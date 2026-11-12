"""One Responses request creates the source and an identical RU/KZ translation."""
import json
from app.modules.assessment.helpers.question_prose_layout import EXPLANATION_AUTHORING_RULES
from copy import deepcopy
from dataclasses import replace
from app.modules.assessment.ai.openai_question_provider import OpenAIQuestionProvider
from app.modules.assessment.ai.question_prompt_builder import AIQuestionPromptBuilder
from app.modules.assessment.ai.question_response_parser import AIQuestionResponseParser
from app.modules.assessment.enums import AssessmentLanguage
from app.modules.assessment.helpers.bilingual_question_contract import source_payload, assert_variant_contract, target_language
from app.modules.assessment.services.assessment_question_validation_service import AssessmentQuestionValidationService as Validator


def question_payload(question):
    payload = source_payload(question)
    payload['text_segments'] = list(payload['text_segments'] or [])
    return payload


def parse_bilingual(raw_output, request):
    from app.modules.assessment.helpers.bilingual_inline_response import expand_inline_response
    from app.modules.assessment.helpers.generation_response_diagnostics import validate_response_envelope
    payload = json.loads(raw_output)
    validate_response_envelope(payload, request.question_count)
    from app.modules.assessment.helpers.element_scoring import inject_parameters
    payload=inject_parameters(payload,request)
    from app.modules.assessment.helpers.ai_source_image import inject_option_assets
    payload = inject_option_assets(payload, getattr(request, 'image_option_keys', ()))
    raw = expand_inline_response(payload)
    source = AIQuestionResponseParser.parse_payload(payload=raw, request=request)
    target = target_language(request.language)
    translated = raw.get('translation')
    if not isinstance(translated, dict) or translated.get('language') != target:
        raise ValueError('AI must return the requested second language in the same response.')
    text_maps = translated.get('text_maps')
    if text_maps is not None:
        if set(translated) != {'language','text_maps'}:
            raise ValueError('Text-map translation must not contain technical objects.')
        if not isinstance(text_maps,list) or len(text_maps) != len(source.questions):
            raise ValueError('One translation text map is required for every source question.')
        from app.modules.assessment.helpers.bilingual_generation_text_map import variant_from_text_map
        # Map addresses belong to the original model JSON. Parsing may split
        # text-with-math into several segments, so never address parsed DTOs.
        from app.modules.assessment.helpers.bilingual_question_contract import FIELDS
        translated_questions = []
        for index,(question,raw_question,text_map) in enumerate(zip(source.questions,raw['questions'],text_maps),1):
            raw_payload = {key:deepcopy(raw_question.get(key)) for key in FIELDS}
            if raw_payload.get('text_segments'):
                # The source parser also treats rich segments as authoritative.
                # Derive its duplicate plain fallback without changing indices.
                raw_payload['text'] = ''.join(
                    '[Сурет]' if seg['type']=='image' else seg.get('text','')
                    for seg in raw_payload['text_segments']).strip()
            try:
                target_payload = variant_from_text_map(raw_payload,question.question_type,text_map)
            except ValueError as exc:
                raise ValueError(f'Bilingual question #{index} (source JSON paths): {exc}') from exc
            target_segments = target_payload.get('text_segments')
            if target_segments:
                # Virtual optional boundary slots are an editor contract, not
                # model segments. The shared parser requires nonempty segments.
                while target_segments and target_segments[0].get('type')=='text' and not target_segments[0].get('text','').strip():
                    target_segments.pop(0)
                while target_segments and target_segments[-1].get('type')=='text' and not target_segments[-1].get('text','').strip():
                    target_segments.pop()
            target_question = deepcopy(raw_question)
            for key,value in target_payload.items():
                # Preserve absence of optional source fields. In particular,
                # explicit text_segments=null is invalid in the shared parser.
                if key in raw_question or value is not None:
                    target_question[key] = value
            translated_questions.append(target_question)
        normalized_target = AIQuestionResponseParser.parse_payload(
            payload={'questions':translated_questions},
            request=replace(request,language=AssessmentLanguage(target)))
        payloads = []
        for index,(a,b) in enumerate(zip(source.questions,normalized_target.questions),1):
            source_data,target_data = question_payload(a),question_payload(b)
            try:
                assert_variant_contract(source_data,target_data,a.question_type)
            except ValueError as exc:
                raise ValueError(f'Bilingual question #{index} (normalized contract): {exc}') from exc
            payloads.append(deepcopy(target_data))
    else:
        # Compatibility: old full-object responses still undergo the same
        # strict protected-contract comparison; differences are not repaired.
        other = AIQuestionResponseParser.parse_payload(payload=translated,
            request=replace(request, language=AssessmentLanguage(target)))
        if len(source.questions) != request.question_count or len(other.questions) != request.question_count:
            raise ValueError('Source and translated arrays must match the requested question count.')
        payloads = []
        for index,(a,b) in enumerate(zip(source.questions,other.questions),1):
            for name in ['question_type','difficulty','max_score','learning_objective_ids']:
                if getattr(a,name) != getattr(b,name):
                    raise ValueError(f'Bilingual question #{index}: the two languages must describe identical tasks.')
            source_data,target_data = question_payload(a),question_payload(b)
            try:
                assert_variant_contract(source_data,target_data,a.question_type)
            except ValueError as exc:
                raise ValueError(f'Bilingual question #{index}: {exc}') from exc
            payloads.append(deepcopy(target_data))
    contract_errors = []
    for index,(question,target_data) in enumerate(zip(source.questions,payloads),1):
        for version,data in [('source',question_payload(question)),('translation',target_data)]:
            try:
                Validator.validate_authoring(question_type=question.question_type,content=data['content'],
                    answer_key=data['answer_key'],grading_settings=data['grading_settings'],max_score=question.max_score)
            except ValueError as exc:
                contract_errors.append(f'Question #{index} ({question.question_type.value}, {version}): {exc}')
    if contract_errors:
        raise ValueError('Question contract errors: '+ '; '.join(contract_errors))
    from app.modules.assessment.helpers.question_creation_plan import validate_plan_response
    validate_plan_response(request,source)
    result = replace(source,metadata=dict(source.metadata,bilingual_payload=payloads[0],
        bilingual_payloads=payloads,bilingual_language=target))
    from app.modules.assessment.helpers.ai_source_image import attach_image
    return attach_image(result, getattr(request, 'source_image_key', None))


class BilingualGenerationProvider(OpenAIQuestionProvider):
    def _get_client(self, *, api_key):
        client = super()._get_client(api_key=api_key)
        return client.with_options(max_retries=0) if hasattr(client, 'with_options') else client

    def _build_prompt(self, request):
        prompt = AIQuestionPromptBuilder.build(request)
        if request.language.value not in ['ru', 'kk']:
            if request.creation_plan:
                return replace(prompt, system_prompt=prompt.system_prompt+'\nFollow this exact ordered plan; each entry is one distinct question with its own unchanged score: '+json.dumps(request.creation_plan))
            return prompt
        if all(row.question_type.value=='single_choice' for row in request.question_types):
            from app.modules.assessment.ai.single_choice_parts_prompt import build_single_choice_prompt
            result=build_single_choice_prompt(prompt,request)
            # Specialized prompts inherit the SAME final explanation contract.
            return replace(result,system_prompt=result.system_prompt.replace(EXPLANATION_AUTHORING_RULES,'')+'\n'+EXPLANATION_AUTHORING_RULES)
        target = target_language(request.language)
        from app.modules.assessment.helpers.generation_slot_rules import generation_plan
        override = r'''
BILINGUAL SHARED-STRUCTURE OVERRIDE — INLINE PROSE (supersedes previous bilingual examples):
Return ONE JSON object with the normal questions array and
"translation":{"language":"TARGET","mode":"inline_v1"}.
Generate technical structure, formulas, numbers, IDs and keys ONLY ONCE.
Instead of a human-language string, emit {"source":"source-language prose",
"translation":"TARGET-language prose"} AT THAT SAME FIELD.
Example text segment: {"type":"text","text":{"source":"Берілген функциялар: ",
"translation":"Даны функции: "}}.
Example math segment: {"type":"latex","text":"f(x)=2x+1"} (one shared string).
Example option: {"value":"A","segments":[{"type":"latex","text":"1.104"}]}.
Numeric-only options have NO prose wrapper and NO separate translation.
Apply bilingual prose pairs to title, instruction, explanation, author_comment,
all human text segments in statement, options, left/right matching columns,
formula meanings, criteria, labels, hints and textual accepted_answers/word_bank
where the type supports translated answers. Translate EVERY human text field.
Never put a pair in question_type, difficulty, IDs, option value, symbol keys,
math/latex strings, numeric answer values, scores, booleans, or media paths.
Do not include text_maps, translation.questions, JSON paths or a second copy
of technical content. No duplicate plain text field when text_segments exist.
Use separate text/latex segments; no prose inside latex, even in \text{...}.
Put ALL givens in the visible text_segments; a plain text fallback is not rendered
when rich segments exist. Preserve numbers and mathematical tokens in prose
translations exactly. Prefer math segments for exponents and expressions.
Use natural word order in both languages, including text BEFORE a formula.
EXACT ORDERED CREATION PLAN follows: each entry describes ONE distinct question.
Use its own type, difficulty, score and counts. Never distribute a slot score
among other questions. slot_id identifies an entry in this plan, not a student
answer; return questions in this exact order. Do not output audit/plan fields.
'''.replace('TARGET', target)
        override += json.dumps(generation_plan(request), ensure_ascii=False)
        override += """
FINAL CONTENT AUDIT BEFORE RETURNING JSON (do not output the audit):
For EVERY question verify the mathematical truth of EVERY option against the
exact criterion in its statement. For multiple_choice the number of genuinely
true options AND the length of answer_key.values must BOTH equal that question's
max_score. For a two-point question use exactly TWO true and TWO false A-D options.
For three points use THREE true and ONE false A-D options.
If more options are true than the slot requires, REWRITE that distractor or the statement before
returning; NEVER merely omit a true option from answer_key.values.
Approximation tasks must explicitly state precision (decimal places, significant
figures, tolerance, or the exact truncation requested). All competing answers
are judged by THAT SAME criterion. Do not mix an exact binomial expansion and
several approximations of different precision as interchangeable true answers.
For single_choice there must be exactly ONE correct option PER PART under that criterion.
Recalculate numeric expressions and rounding. Use '=' only for exact identities;
use approximate notation for rounded/truncated values. Keep every numeric/formula
token unchanged in translation, including intermediate values in explanations.
Each question must assess the ACTION in the selected learning objective, not
merely mention its topic. If the goal is APPLYING a formula to approximate
values, require that application in single_choice, multiple_choice, matching
and formula parts alike. A recall question asking for the formula itself or
names of its terms does not satisfy that application goal.
Advanced difficulty must require deeper reasoning (e.g. comparing approximations,
choosing a suitable truncation or analysing an error), not just more pairs.
Ensure explanation agrees with the statement, every correct option and the key.
For Russian statements use natural word order with a text segment before
the first formula when needed; avoid a literal Kazakh-order sentence.
Do not add audit fields or reasoning to the output JSON.
"""
        override += "\nWEIGHTED ELEMENTS V2 OVERRIDE: For slots with element_score_policy=weighted_elements_v2, use EXACTLY element_count independently answered elements per card, NEVER max_score elements. One correct element earns points_per_element; max_score is the specified product. Return one common statement per card; do not repeat only the first part in the common statement. Use existing per_part/per_pair/per_gap policies and structure, the server attaches the trusted weight metadata. multiple_choice has exactly option_count options and correct_option_count true options; its full exact answer set earns points_per_element, otherwise zero. short_text/image_choice contain one question per card; make more cards for more such questions. manual_review criteria must match criterion_points individually, with their sum equal to max_score. Never derive counts from points. This overrides earlier score-count examples and all 'one point' instructions for weighted slots. Return every requested card, source and translation in inline_v1 in one valid JSON document.\n"
        return replace(prompt, system_prompt=prompt.system_prompt+'\n'+override)

    def _parse_response(self, raw_output, request):
        self.last_generation_output = raw_output
        if request.language.value not in ['ru', 'kk']:
            return super()._parse_response(raw_output, request)
        try:
            return parse_bilingual(raw_output, request)
        except (ValueError, TypeError) as exc:
            # The web service may retain this candidate without another provider call.
            exc.generation_candidate = raw_output
            import logging
            from app.modules.assessment.helpers.bilingual_failure_diagnostics import save_failure
            logger = logging.getLogger(__name__)
            try:
                path = save_failure(raw_output, request, exc, response_metadata=getattr(self, 'last_response_metadata', None))
                logger.error('Bilingual diagnostic file (offline replay): %s', path)
            except Exception:
                logger.error('Could not save bilingual diagnostic file; original validation error follows.')
            raise
