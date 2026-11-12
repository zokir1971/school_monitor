document.addEventListener(
    "DOMContentLoaded",
    () => {

      // ===================================================
      // STEP 1 — SUBJECT + GRADE
      // ===================================================

      const scopeRadios =
        document.querySelectorAll(
          'input[name="scope"]'
        );

      const subjectInput =
        document.getElementById(
          "subject_id"
        );

      const gradeInput =
        document.getElementById(
          "grade_level"
        );

      const scopeSubmit =
        document.getElementById(
          "scope-submit"
        );


      function updateScopeSelection(
        radio
      ) {

        if (
          !radio
          ||
          !radio.checked
        ) {
          return;
        }

        if (subjectInput) {
          subjectInput.value =
            radio.dataset.subjectId || "";
        }

        if (gradeInput) {
          gradeInput.value =
            radio.dataset.gradeLevel || "";
        }

        if (scopeSubmit) {
          scopeSubmit.disabled = false;
        }
      }


      scopeRadios.forEach(
        (radio) => {

          radio.addEventListener(
            "change",
            () => {
              updateScopeSelection(
                radio
              );
            }
          );

        }
      );


      const checkedScope =
        document.querySelector(
          'input[name="scope"]:checked'
        );

      if (checkedScope) {
        updateScopeSelection(
          checkedScope
        );
      }


      // ===================================================
      // STEP 3 — ONE LEARNING OBJECTIVE
      // ===================================================

      const objectiveRadios =
        document.querySelectorAll(
          'input[name="objective_id"]'
        );

      const objectiveSubmit =
        document.getElementById(
          "objective-submit"
        );


      function updateObjectiveSubmit() {

        if (!objectiveSubmit) {
          return;
        }

        const selectedObjective =
          document.querySelector(
            'input[name="objective_id"]:checked'
          );

        objectiveSubmit.disabled =
          !selectedObjective;
      }


      objectiveRadios.forEach(
        (radio) => {

          radio.addEventListener(
            "change",
            updateObjectiveSubmit
          );

        }
      );


      updateObjectiveSubmit();


      // ===================================================
      // STEP 4 — QUESTION TYPE
      // ===================================================

      const questionType =
        document.getElementById(
          "question_type"
        );

      const questionFieldGroups =
        document.querySelectorAll(
          "[data-question-fields]"
        );


      // ===================================================
      // DISABLE ALL TYPE-SPECIFIC FIELDS
      // ===================================================

      function resetQuestionTypeFields() {
        document.getElementById("max_score")?.setCustomValidity("");

        questionFieldGroups.forEach(
          (group) => {

            const inputs =
              group.querySelectorAll(
                "[data-type-input]"
              );

            inputs.forEach(
              (input) => {

                /*
                 * Поля неактивного типа:
                 *
                 * 1. не участвуют в HTML validation;
                 * 2. не отправляются в POST;
                 * 3. не конфликтуют с полями
                 *    других типов.
                 */

                input.required = false;
                input.disabled = true;

              }
            );

            group.hidden = true;

          }
        );

      }


      // ===================================================
      // ACTIVATE SELECTED TYPE
      // ===================================================

      function configureManualReview(group) {
        group.querySelectorAll('[data-manual-required]').forEach(input => input.required = true);
        updateManualTotal();
      }

      let manualMaximumError = '';
      function updateManualTotal() {
        const group = document.getElementById('manual-review-fields');
        const maximum = document.getElementById('max_score');
        if (!group || !maximum) return;
        const scores = [...group.querySelectorAll('[name="manual_criterion_score"]')];
        if (questionType?.value !== 'manual_review') {
          if (manualMaximumError && maximum.validationMessage === manualMaximumError) maximum.setCustomValidity('');
          manualMaximumError = '';
          scores.forEach(input => input.setCustomValidity(''));
          return;
        }
        const max = Number(maximum.value);
        const validMaximum = Number.isSafeInteger(max) && max >= 1 && max <= 99999999;
        const values = scores.map(input => Number(input.value));
        const valid = values.every(value => Number.isSafeInteger(value) && value >= 1 && value <= 99999999);
        scores.forEach((input, index) => input.setCustomValidity(
          Number.isSafeInteger(values[index]) && values[index] >= 1 && values[index] <= 99999999
            ? '' : window.SchoolMonitorI18n.t("qb_2fe7fb38ccb2")
        ));
        const total = values.reduce((sum, value) => sum + value, 0);
        let message = '';
        if (!validMaximum) message = window.SchoolMonitorI18n.t("qb_cf34b842c450");
        else if (!scores.length || scores.length > Math.min(50, max)) message = window.SchoolMonitorI18n.t("qb_1be0aa90ed19");
        else if (!valid) message = window.SchoolMonitorI18n.t("qb_1ba460609e11");
        else if (total !== max) message = window.SchoolMonitorI18n.t("qb_e991caebc8b4");
        manualMaximumError = message;
        maximum.setCustomValidity(message);
        group.querySelector('[data-manual-total]').textContent = valid && validMaximum
          ? window.SchoolMonitorI18n.t("qb_6a91d572f139", {p0: (total), p1: (max), p2: (message || window.SchoolMonitorI18n.t("qb_caa0f8bd78ca"))})
          : message;
        refreshManualButtons();
      }

      function addManualCriterion(criterion = null) {
        const group = document.getElementById('manual-review-fields');
        if (!group) throw new Error('Manual review component missing');
        const list = group.querySelector('[data-manual-criteria]');
        const count = list.children.length;
        if (count >= 50) return;
        const existing = [...list.querySelectorAll('[name="manual_criterion_id"]')].map(i => Number(i.value.slice(1)));
        const next = Math.max(Number(list.dataset.lastId || 0), 0, ...existing) + 1;
        const id = criterion?.id || `C${next}`;
        list.dataset.lastId = String(Math.max(next, Number(id.slice(1)) || 0));
        const row = document.createElement('div');
        row.className = 'qb-manual-criterion';
        const header = document.createElement('div');
        header.className = 'qb-manual-criterion__header';
        const heading = document.createElement('strong');
        heading.textContent = id;
        const hidden = document.createElement('input');
        hidden.type = 'hidden'; hidden.name = 'manual_criterion_id'; hidden.value = id;
        hidden.setAttribute('data-type-input', '');
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'qb-remove-answer'; remove.textContent = window.SchoolMonitorI18n.t("qb_75d34f88ede8");
        remove.addEventListener('click', () => {
          if (list.children.length <= 1) return;
          row.remove(); refreshManualButtons(); updateManualTotal();
        });
        header.append(heading, hidden, remove);
        const fields = document.createElement('div');
        fields.className = 'qb-manual-criterion__fields';
        for (const [name, labelText, type, value] of [
          ['manual_criterion_title', window.SchoolMonitorI18n.t("qb_3374f5db69b6"), 'text', criterion?.title || ''],
          ['manual_criterion_score', window.SchoolMonitorI18n.t("qb_efefc3289ab0"), 'number', criterion?.max_score ?? ''],
          ['manual_criterion_description', window.SchoolMonitorI18n.t("qb_06f8d3b50925"), 'textarea', criterion?.description || '']
        ]) {
          const field = document.createElement('div'); field.className = 'qb-form-field';
          if (type === 'textarea') field.classList.add('qb-manual-criterion__description');
          const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
          if (type !== 'textarea') input.type = type;
          input.name = name; input.id = `${name}-${id}`; input.value = String(value);
          input.className = 'qb-form-control'; input.setAttribute('data-type-input', '');
          input.setAttribute('data-manual-required', '');
          if (type === 'number') { input.min = '1'; input.max = '99999999'; input.step = '1'; }
          else input.maxLength = type === 'textarea' ? 2000 : 200;
          const label = document.createElement('label'); label.htmlFor = input.id;
          label.className = 'qb-form-label'; label.textContent = labelText;
          field.append(label, input); fields.append(field);
        }
        row.append(header, fields); list.append(row);
        row.querySelectorAll('[data-type-input]').forEach(input => {
          input.disabled = questionType?.value !== 'manual_review';
          input.required = !input.disabled && input.hasAttribute('data-manual-required');
        });
        refreshManualButtons(); updateManualTotal();
      }

      function refreshManualButtons() {
        const group = document.getElementById('manual-review-fields');
        if (!group) return;
        const list = group.querySelector('[data-manual-criteria]');
        const maximum = Number(document.getElementById('max_score')?.value);
        const limit = questionType?.value === 'manual_review' && Number.isSafeInteger(maximum) && maximum >= 1
          ? Math.min(50, maximum) : 50;
        group.querySelector('[data-manual-add]').disabled = list.children.length >= limit;
        list.querySelectorAll('.qb-remove-answer').forEach(button => button.disabled = list.children.length <= 1);
      }

      function addFormulaMeaningRow(symbol = '', meaning = '') {
        const group = document.getElementById('formula-fields');
        const list = group.querySelector('[data-formula-variables]');
        if (list.children.length >= 30) return;
        const row = document.createElement('div'); row.className = 'qb-formula-meaning-row';
        for (const [name, labelText, value, max] of [
          ['formula_symbol', window.SchoolMonitorI18n.t("qb_2a407c58f54d"), symbol, 80], ['formula_meaning', window.SchoolMonitorI18n.t("qb_dd35bf636b0f"), meaning, 200]
        ]) {
          const label = document.createElement('label'); label.className = 'qb-form-label';
          const caption = document.createElement('span'); caption.textContent = labelText;
          const input = document.createElement('input'); input.type = 'text'; input.name = name;
          input.value = value; input.maxLength = max; input.className = 'qb-form-control';
          input.setAttribute('data-type-input', ''); input.setAttribute('data-formula-required', '');
          input.disabled = questionType?.value !== 'formula'; input.required = !input.disabled;
          label.append(caption, input); row.append(label);
        }
        const remove = document.createElement('button'); remove.type = 'button';
        remove.className = 'qb-formula-remove'; remove.textContent = window.SchoolMonitorI18n.t("qb_d6e61de8581e");
        remove.addEventListener('click', () => {
          if (list.children.length <= 1) return;
          row.remove(); refreshFormulaButtons();
        });
        row.append(remove); list.append(row); refreshFormulaButtons();
      }

      function addFormulaDistractor(value = '') {
        const group = document.getElementById('formula-fields');
        const list = group.querySelector('[data-formula-distractors]');
        if (list.children.length >= 20) return;
        const row = document.createElement('div'); row.className = 'qb-formula-distractor-row';
        const label = document.createElement('label'); label.className = 'qb-form-label';
        const text = document.createElement('span'); text.textContent = window.SchoolMonitorI18n.t("qb_a30130594681");
        const input = document.createElement('input'); input.type = 'text'; input.name = 'formula_distractor';
        input.value = value; input.maxLength = 200; input.className = 'qb-form-control';
        input.setAttribute('data-type-input', ''); input.disabled = questionType?.value !== 'formula';
        label.append(text, input);
        const remove = document.createElement('button'); remove.type = 'button';
        remove.className = 'qb-formula-remove'; remove.textContent = window.SchoolMonitorI18n.t("qb_d6e61de8581e");
        remove.addEventListener('click', () => { row.remove(); refreshFormulaButtons(); });
        row.append(label, remove); list.append(row); refreshFormulaButtons();
      }

      function refreshFormulaButtons() {
        const group = document.getElementById('formula-fields');
        if (!group) return;
        const list = group.querySelector('[data-formula-variables]');
        list.querySelectorAll('.qb-formula-remove').forEach(button => button.disabled = list.children.length <= 1);
        group.querySelector('[data-formula-variable-add]').disabled = list.children.length >= 30;
        group.querySelector('[data-formula-distractor-add]').disabled = group.querySelector('[data-formula-distractors]').children.length >= 20;
      }

      function activateQuestionGroup(
        questionTypeValue
      ) {

        const activeGroup =
          document.querySelector(
            `[data-question-fields="${questionTypeValue}"]`
          );

        if (!activeGroup) {
          return null;
        }

        activeGroup.hidden = false;

        const inputs =
          activeGroup.querySelectorAll(
            "[data-type-input]"
          );

        inputs.forEach(
          (input) => {
            input.disabled = false;
          }
        );

        return activeGroup;
      }


      // ===================================================
      // SINGLE CHOICE
      // ===================================================

      function configureSingleChoice(
        group
      ) {

        if (!group) {
          return;
        }

        if (group.dataset.scMultipart === '1') return;
        const optionInputs =
          group.querySelectorAll(
            'input[type="text"]'
          );

        optionInputs.forEach(
          (input) => {
            input.required = true;
          }
        );

        const correctAnswer =
          group.querySelector(
            'input[name="correct_answer"]'
          );

        if (correctAnswer) {
          correctAnswer.required = true;
        }
      }


      // ===================================================
      // MULTIPLE CHOICE
      // ===================================================

      function configureMultipleChoice(
        group
      ) {

        if (!group) {
          return;
        }

        const optionInputs =
          group.querySelectorAll(
            'input[type="text"]'
          );

        optionInputs.forEach(
          (input) => {
            input.required = true;
          }
        );

        /*
         * Checkbox-ам required не ставим.
         *
         * Иначе браузер потребует отметить
         * каждый checkbox.
         *
         * Проверка "хотя бы один правильный"
         * выполняется отдельно перед submit.
         */
      }


      // ===================================================
      // TRUE / FALSE
      // ===================================================

      function configureTrueFalse(
        group
      ) {

        if (!group) {
          return;
        }

        const correctAnswer =
          group.querySelector(
            'input[name="correct_answer"]'
          );

        if (correctAnswer) {
          correctAnswer.required = true;
        }
      }


      // ===================================================
      // SHORT TEXT
      // ===================================================

      function configureShortText(
        group
      ) {

        if (!group) {
          return;
        }

        /*
         * Обязательным делаем только
         * первое поле.
         *
         * Остальные accepted_answers —
         * альтернативные и могут быть пустыми.
         */

        const firstAnswer =
          group.querySelector(
            'input[name="accepted_answers"]'
          );

        if (firstAnswer) {
          firstAnswer.required = true;
        }
      }


      // ===================================================
      // NUMBER
      // ===================================================

      function configureNumber(
        group
      ) {

        if (!group) {
          return;
        }

        const numberAnswer =
          group.querySelector(
            'input[name="number_answer"]'
          );

        if (numberAnswer) {
          numberAnswer.required = true;
        }
      }

      function configureMatching(
        group
      ) {

        if (!group) {
          return;
        }

        const inputs =
          group.querySelectorAll(
            'input[name="matching_left"], ' +
            'input[name="matching_right"]'
          );

        inputs.forEach(
          (input) => {
            input.required = true;
          }
        );
      }

      // ===================================================
      // ORDERING
      // ===================================================

      function configureOrdering(
        group
      ) {

        if (!group) {
         return;
        }

        const inputs =
          group.querySelectorAll(
            'input[name="ordering_item"]'
          );

        /*
        * Первые две позиции обязательны.
        *
        * Динамически добавленные строки
        * можно оставить пустыми — helper
        * их отбросит.
        */

        inputs.forEach(
          (input, index) => {
            input.required =
              index < 2;
          }
        );
      }

      // ===================================================
      // FILL GAPS
      // ===================================================

      function configureFillGaps(
      group
      ) {

        if (!group) {
         return;
        }

        const sourceText =
            group.querySelector(
            'textarea[name="fill_gaps_text"]'
            );

        if (sourceText) {
            sourceText.required = true;
        }

        const modes =
            group.querySelectorAll(
            'input[name="fill_gaps_mode"]'
            );

        modes.forEach(
            (input) => {
            input.required = true;
            }
        );

        updateFillGapsMode();
      }

      // ===================================================
      // UPDATE QUESTION TYPE
      // ===================================================

      function updateQuestionTypeFields() {

        if (!questionType) {
          return;
        }

        resetQuestionTypeFields();

        const selectedType =
          questionType.value;

        const activeGroup =
          activateQuestionGroup(
            selectedType
          );

        if (!activeGroup) {
          return;
        }


        switch (selectedType) {
          case "image_choice":
            activeGroup.querySelectorAll('[name="image_correct_answer"]').forEach(input => input.required = true);
            break;
          case "formula": {
            const answer = activeGroup.querySelector('[name="formula_answer"]');
            if (answer) answer.required = true;
            activeGroup.querySelectorAll("[data-formula-required]").forEach(input => input.required = true);
            break;
          }
          case "manual_review":
            configureManualReview(activeGroup);
            break;

          case "single_choice":

            configureSingleChoice(
              activeGroup
            );

            break;


          case "multiple_choice":

            configureMultipleChoice(
              activeGroup
            );

            break;


          case "true_false":

            configureTrueFalse(
              activeGroup
            );

            break;


          case "short_text":

            configureShortText(
              activeGroup
            );

            break;


          case "number":

            configureNumber(
              activeGroup
            );

            break;

          case "matching":

            configureMatching(
              activeGroup
            );

            break;

          case "ordering":

            configureOrdering(
              activeGroup
            );

            break;

          case "fill_gaps":

            configureFillGaps(
                activeGroup
            );

            break;

          default:
            break;
        }
      }


      if (questionType) {

        questionType.addEventListener(
          "change",
          updateQuestionTypeFields
        );

        /*
         * Сразу активируем поля
         * выбранного типа при загрузке.
         */

        // Initial activation runs after fill-gaps controls exist.
      }


      // ===================================================
      // SHORT TEXT — DYNAMIC ACCEPTED ANSWERS
      // ===================================================

      const acceptedAnswersContainer =
        document.getElementById(
          "accepted-answers-container"
        );

      const addAcceptedAnswerButton =
        document.getElementById(
          "add-accepted-answer"
        );


      function updateAcceptedAnswerRows() {

        if (!acceptedAnswersContainer) {
          return;
        }

        const rows =
          acceptedAnswersContainer
            .querySelectorAll(
              "[data-accepted-answer-row]"
            );

        rows.forEach(
          (row) => {

            const removeButton =
              row.querySelector(
                "[data-remove-answer]"
              );

            if (!removeButton) {
              return;
            }

            /*
             * Одно поле accepted_answers
             * всегда должно оставаться.
             */

            const onlyOne =
              rows.length <= 1;

            removeButton.hidden =
              onlyOne;

            removeButton.disabled =
              onlyOne;

          }
        );
      }


      function createAcceptedAnswerRow() {

        if (!acceptedAnswersContainer) {
          return;
        }

        const row =
          document.createElement(
            "div"
          );

        row.className =
          "qb-short-answer-row";

        row.setAttribute(
          "data-accepted-answer-row",
          ""
        );


        // -----------------------------------------------
        // INPUT
        // -----------------------------------------------

        const input =
          document.createElement(
            "input"
          );

        input.type = "text";

        input.name =
          "accepted_answers";

        input.className =
          "qb-form-control";

        input.placeholder =
          window.SchoolMonitorI18n.t("qb_8a641d7b8c66");

        input.setAttribute(
          "data-type-input",
          ""
        );

        /*
         * Новое поле активно только тогда,
         * когда сейчас выбран SHORT_TEXT.
         */

        input.disabled =
          !questionType
          ||
          questionType.value
          !== "short_text";


        // -----------------------------------------------
        // REMOVE BUTTON
        // -----------------------------------------------

        const removeButton =
          document.createElement(
            "button"
          );

        removeButton.type =
          "button";

        removeButton.className =
          "qb-remove-answer";

        removeButton.textContent =
          "×";

        removeButton.setAttribute(
          "data-remove-answer",
          ""
        );

        removeButton.setAttribute(
          "aria-label",
          window.SchoolMonitorI18n.t("qb_5bc9db1eee37")
        );


        // -----------------------------------------------
        // APPEND
        // -----------------------------------------------

        row.appendChild(
          input
        );

        row.appendChild(
          removeButton
        );

        acceptedAnswersContainer
          .appendChild(
            row
          );

        updateAcceptedAnswerRows();

        input.focus();
      }


      if (addAcceptedAnswerButton) {

        addAcceptedAnswerButton
          .addEventListener(
            "click",
            createAcceptedAnswerRow
          );
      }


      /*
       * Event delegation.
       *
       * Работает и для строк,
       * созданных после загрузки страницы.
       */

      if (acceptedAnswersContainer) {

        acceptedAnswersContainer
          .addEventListener(
            "click",
            (event) => {

              const target =
                event.target;

              if (
                !(target instanceof Element)
              ) {
                return;
              }

              const removeButton =
                target.closest(
                  "[data-remove-answer]"
                );

              if (!removeButton) {
                return;
              }

              const row =
                removeButton.closest(
                  "[data-accepted-answer-row]"
                );

              if (!row) {
                return;
              }

              const rows =
                acceptedAnswersContainer
                  .querySelectorAll(
                    "[data-accepted-answer-row]"
                  );

              /*
               * Защита:
               * последнюю строку удалить нельзя.
               */

              if (rows.length <= 1) {
                return;
              }

              row.remove();

              updateAcceptedAnswerRows();

            }
          );
      }


      updateAcceptedAnswerRows();

      // ===================================================
      // MATCHING — DYNAMIC PAIRS
      // ===================================================

      const matchingPairsContainer =
        document.getElementById(
          "matching-pairs-container"
        );

      const addMatchingPairButton =
        document.getElementById(
          "add-matching-pair"
        );


      function updateMatchingRows() {

        if (!matchingPairsContainer) {
          return;
        }

        const rows =
          matchingPairsContainer
            .querySelectorAll(
              "[data-matching-row]"
            );

        rows.forEach(
          (row) => {

            const removeButton =
              row.querySelector(
                "[data-remove-matching]"
              );

            if (!removeButton) {
              return;
            }

            const onlyOne =
              rows.length <= 1;

            removeButton.hidden =
              onlyOne;

            removeButton.disabled =
              onlyOne;

          }
        );
      }


      function createMatchingRow() {

        if (!matchingPairsContainer) {
          return;
        }

        const row =
          document.createElement(
            "div"
          );

        row.className =
          "qb-matching-row";

        row.setAttribute(
          "data-matching-row",
          ""
        );


        // LEFT

        const leftField =
          document.createElement(
            "div"
          );

        leftField.className =
          "qb-matching-field";


        const leftLabel =
          document.createElement(
            "label"
          );

        leftLabel.className =
          "qb-form-label";

        leftLabel.textContent =
          window.SchoolMonitorI18n.t("qb_79fad5ef96a5");


        const leftInput =
          document.createElement(
            "input"
          );

        leftInput.type = "text";
        leftInput.name = "matching_left";

        leftInput.className =
          "qb-form-control";

        leftInput.placeholder =
          window.SchoolMonitorI18n.t("qb_f2a33bef84db");

        leftInput.setAttribute(
          "data-type-input",
          ""
        );


        // ARROW

        const arrow =
          document.createElement(
            "div"
          );

        arrow.className =
          "qb-matching-arrow";

        arrow.textContent = "↔";

        arrow.setAttribute(
          "aria-hidden",
          "true"
        );


        // RIGHT

        const rightField =
          document.createElement(
            "div"
          );

        rightField.className =
    "qb-matching-field";


        const rightLabel =
          document.createElement(
      "label"
          );

        rightLabel.className =
          "qb-form-label";

        rightLabel.textContent =
          window.SchoolMonitorI18n.t("qb_7273229352c1");


        const rightInput =
          document.createElement(
            "input"
          );

        rightInput.type = "text";
        rightInput.name = "matching_right";

        rightInput.className =
          "qb-form-control";

        rightInput.placeholder =
          window.SchoolMonitorI18n.t("qb_f5b05c470b76");

        rightInput.setAttribute(
          "data-type-input",
          ""
        );


        // REMOVE

        const removeButton =
          document.createElement(
            "button"
          );

        removeButton.type =
          "button";

        removeButton.className =
          "qb-remove-answer qb-matching-remove";

        removeButton.textContent =
          "×";

        removeButton.setAttribute(
          "data-remove-matching",
          ""
        );

        removeButton.setAttribute(
          "aria-label",
          window.SchoolMonitorI18n.t("qb_483f8060356e")
        );


        // BUILD

        leftField.appendChild(
          leftLabel
        );

        leftField.appendChild(
          leftInput
        );

        rightField.appendChild(
          rightLabel
        );

        rightField.appendChild(
          rightInput
        );

        row.appendChild(
          leftField
        );

        row.appendChild(
          arrow
        );

        row.appendChild(
          rightField
        );

        row.appendChild(
          removeButton
        );


        matchingPairsContainer
          .appendChild(
            row
          );


        /*
        * Кнопка доступна только при
        * открытом MATCHING, поэтому новая
        * строка сразу активна.
        */

        const matchingIsActive =
          questionType
          &&
          questionType.value === "matching";

        leftInput.disabled =
          !matchingIsActive;

        rightInput.disabled =
          !matchingIsActive;

        leftInput.required =
          matchingIsActive;

        rightInput.required =
          matchingIsActive;


        updateMatchingRows();

        leftInput.focus();
      }


      if (addMatchingPairButton) {

        addMatchingPairButton
          .addEventListener(
            "click",
            createMatchingRow
          );
      }


      if (matchingPairsContainer) {

        matchingPairsContainer
          .addEventListener(
            "click",
            (event) => {

              const target =
                event.target;

              if (
                !(target instanceof Element)
              ) {
                return;
              }

              const removeButton =
                target.closest(
                  "[data-remove-matching]"
                );

              if (!removeButton) {
                return;
              }

              const rows =
                matchingPairsContainer
                  .querySelectorAll(
                    "[data-matching-row]"
                  );

              if (rows.length <= 1) {
                return;
              }

              const row =
                removeButton.closest(
                 "[data-matching-row]"
                );

              if (!row) {
                return;
              }

              row.remove();

              updateMatchingRows();

            }
          );
      }


      updateMatchingRows();

      // ===================================================
      // ORDERING — DYNAMIC ITEMS
      // ===================================================

      const orderingItemsContainer =
      document.getElementById(
          "ordering-items-container"
      );

      const addOrderingItemButton =
      document.getElementById(
          "add-ordering-item"
      );


      function updateOrderingRows() {

      if (!orderingItemsContainer) {
          return;
      }

      const rows =
          orderingItemsContainer
          .querySelectorAll(
              "[data-ordering-row]"
          );

      rows.forEach(
          (row, index) => {

      // -----------------------------------------------
      // NUMBER
      // -----------------------------------------------

      const number =
        row.querySelector(
          "[data-ordering-number]"
        );

      if (number) {
        number.textContent =
          String(index + 1);
      }


      // -----------------------------------------------
      // INPUT
      // -----------------------------------------------

      const input =
        row.querySelector(
          'input[name="ordering_item"]'
        );

      if (input) {

        /*
         * Минимум первые два элемента
         * должны быть заполнены.
         */

        input.required =
          questionType
          &&
          questionType.value === "ordering"
          &&
          index < 2;
      }


      // -----------------------------------------------
      // REMOVE
      // -----------------------------------------------

      const removeButton =
        row.querySelector(
          "[data-remove-ordering]"
        );

      if (removeButton) {

        /*
         * Нельзя уменьшить список
         * ниже двух элементов.
         */

        const minimumReached =
          rows.length <= 2;

        removeButton.hidden =
          minimumReached;

        removeButton.disabled =
          minimumReached;
      }

    }
  );
}


function createOrderingRow() {

  if (!orderingItemsContainer) {
    return;
  }

  const row =
    document.createElement(
      "div"
    );

  row.className =
    "qb-ordering-row";

  row.setAttribute(
    "data-ordering-row",
    ""
  );


  // -----------------------------------------------
  // NUMBER
  // -----------------------------------------------

  const number =
    document.createElement(
      "div"
    );

  number.className =
    "qb-ordering-number";

  number.setAttribute(
    "data-ordering-number",
    ""
  );


  // -----------------------------------------------
  // INPUT
  // -----------------------------------------------

  const input =
    document.createElement(
      "input"
    );

  input.type =
    "text";

  input.name =
    "ordering_item";

  input.className =
    "qb-form-control";

  input.placeholder =
    window.SchoolMonitorI18n.t("qb_354446f2a1ae");

  input.setAttribute(
    "data-type-input",
    ""
  );


  const orderingIsActive =
    questionType
    &&
    questionType.value === "ordering";

  input.disabled =
    !orderingIsActive;


  // -----------------------------------------------
  // REMOVE
  // -----------------------------------------------

  const removeButton =
    document.createElement(
      "button"
    );

  removeButton.type =
    "button";

  removeButton.className =
    "qb-remove-answer";

  removeButton.textContent =
    "×";

  removeButton.setAttribute(
    "data-remove-ordering",
    ""
  );

  removeButton.setAttribute(
    "aria-label",
    window.SchoolMonitorI18n.t("qb_62f3d64991de")
  );


  // -----------------------------------------------
  // BUILD
  // -----------------------------------------------

  row.appendChild(
    number
  );

  row.appendChild(
    input
  );

  row.appendChild(
    removeButton
  );

  orderingItemsContainer
    .appendChild(
      row
    );

  updateOrderingRows();

  input.focus();
}


if (addOrderingItemButton) {

  addOrderingItemButton
    .addEventListener(
      "click",
      createOrderingRow
    );
}


if (orderingItemsContainer) {

  orderingItemsContainer
    .addEventListener(
      "click",
      (event) => {

        const target =
          event.target;

        if (
          !(target instanceof Element)
        ) {
          return;
        }

        const removeButton =
          target.closest(
            "[data-remove-ordering]"
          );

        if (!removeButton) {
          return;
        }

        const rows =
          orderingItemsContainer
            .querySelectorAll(
              "[data-ordering-row]"
            );

        /*
         * ORDERING требует минимум
         * два элемента.
         */

        if (rows.length <= 2) {
          return;
        }

        const row =
          removeButton.closest(
            "[data-ordering-row]"
          );

        if (!row) {
          return;
        }

        row.remove();

        /*
         * После удаления автоматически
         * пересчитываем 1, 2, 3...
         */

        updateOrderingRows();

      }
    );
}


updateOrderingRows();

      // ===================================================
// FILL GAPS
// ===================================================

const fillGapsText =
  document.getElementById(
    "fill_gaps_text"
  );

const fillGapsPreviewSection =
  document.getElementById(
    "fill-gaps-preview-section"
  );

const fillGapsPreview =
  document.getElementById(
    "fill-gaps-preview"
  );

const fillGapsSettings =
  document.getElementById(
    "fill-gaps-settings"
  );

const fillWordBankSection =
  document.getElementById(
    "fill-word-bank-section"
  );

const fillWordBankContainer =
  document.getElementById(
    "fill-word-bank-container"
  );

const addFillWordButton =
  document.getElementById(
    "add-fill-word"
  );


function getFillGapsMode() {

  const checked =
    document.querySelector(
      'input[name="fill_gaps_mode"]:checked'
    );

  return checked
    ? checked.value
    : null;
}


// ===================================================
// MODE
// ===================================================

function updateFillGapsMode() {

  const mode =
    getFillGapsMode();

  const wordBankActive =
    mode === "word_bank";

  if (fillWordBankSection) {
    fillWordBankSection.hidden =
      !wordBankActive;
  }

  if (fillWordBankContainer) {

    const inputs =
      fillWordBankContainer
        .querySelectorAll(
          'input[name="fill_word_bank"]'
        );

    inputs.forEach(
      (input) => {

        const fillGapsActive =
          questionType
          &&
          questionType.value
            === "fill_gaps";

        input.disabled =
          !fillGapsActive
          ||
          !wordBankActive;
      }
    );
  }
}


document
  .querySelectorAll(
    'input[name="fill_gaps_mode"]'
  )
  .forEach(
    (radio) => {

      radio.addEventListener(
        "change",
        updateFillGapsMode
      );

    }
  );


// ===================================================
// PARSE [[ANSWER]]
// ===================================================

function parseFillGapsSource(
  source
) {

  const gaps = [];

  const pattern =
    /\[\[(.+?)]]/g;

  let match;

  while (
    (
      match =
        pattern.exec(source)
    ) !== null
  ) {

    const answer =
      match[1].trim();

    gaps.push(
      {
        id:
          `G${gaps.length + 1}`,

        answer: answer,

        start: match.index,

        end:
          pattern.lastIndex
      }
    );
  }

  return gaps;
}


// ===================================================
// SAVE CURRENT ALTERNATIVES
// ===================================================

function collectFillGapAlternatives() {

  const result = {};

  if (!fillGapsSettings) {
    return result;
  }

  const cards =
    fillGapsSettings
      .querySelectorAll(
        "[data-fill-gap-card]"
      );

  cards.forEach(
    (card) => {

      const gapId =
        card.dataset.gapId;

      if (!gapId) {
        return;
      }

      result[gapId] =
        Array.from(
          card.querySelectorAll(
            'input[data-fill-alternative]'
          )
        )
          .map(
            (input) =>
              input.value
          );
    }
  );

  return result;
}


// ===================================================
// ALTERNATIVE ROW
// ===================================================

function createFillAlternativeRow(
  gapId,
  value = ""
) {

  const row =
    document.createElement(
      "div"
    );

  row.className =
    "qb-short-answer-row";


  const input =
    document.createElement(
      "input"
    );

  input.type =
    "text";

  input.name =
    `fill_gap_alternatives_${gapId}`;

  input.className =
    "qb-form-control";

  input.placeholder =
    window.SchoolMonitorI18n.t("qb_78d617894eec");

  input.value =
    value;

  input.setAttribute(
    "data-fill-alternative",
    ""
  );

  input.setAttribute(
    "data-type-input",
    ""
  );


  const fillGapsActive =
    questionType
    &&
    questionType.value
      === "fill_gaps";

  input.disabled =
    !fillGapsActive;


  const removeButton =
    document.createElement(
      "button"
    );

  removeButton.type =
    "button";

  removeButton.className =
    "qb-remove-answer";

  removeButton.textContent =
    "×";

  removeButton.setAttribute(
    "data-remove-fill-alternative",
    ""
  );

  removeButton.setAttribute(
    "aria-label",
    window.SchoolMonitorI18n.t("qb_51b74f94aed0")
  );


  row.appendChild(
    input
  );

  row.appendChild(
    removeButton
  );

  return row;
}


// ===================================================
// GAP CARD
// ===================================================

function createFillGapCard(
  gap,
  previousAlternatives
) {

  const card =
    document.createElement(
      "div"
    );

  card.className =
    "qb-fill-gap-card";

  card.setAttribute(
    "data-fill-gap-card",
    ""
  );

  card.dataset.gapId =
    gap.id;


  const header =
    document.createElement(
      "div"
    );

  header.className =
    "qb-fill-gap-card__header";


  const title =
    document.createElement(
      "div"
    );

  title.className =
    "qb-fill-gap-card__title";

  title.textContent =
    window.SchoolMonitorI18n.t("qb_b67604adfe63", {p0: (gap.id.replace(/^G/, '')+')')});


  const answer =
    document.createElement(
      "div"
    );

  answer.className =
    "qb-fill-gap-card__answer";

  answer.textContent =
    window.SchoolMonitorI18n.t("qb_404f6a237429", {p0: (gap.answer)});


  header.appendChild(
    title
  );

  header.appendChild(
    answer
  );


  const hint =
    document.createElement(
      "div"
    );

  hint.className =
    "qb-form-hint";

  hint.textContent =
    window.SchoolMonitorI18n.t("qb_930d0f1101ee");


  const alternatives =
    document.createElement(
      "div"
    );

  alternatives.className =
    "qb-fill-alternatives";

  alternatives.setAttribute(
    "data-fill-alternatives",
    ""
  );


  const savedValues =
    previousAlternatives[
      gap.id
    ] || [];

  savedValues.forEach(
    (value) => {

      alternatives.appendChild(
        createFillAlternativeRow(
          gap.id,
          value
        )
      );

    }
  );


  const addButton =
    document.createElement(
      "button"
    );

  addButton.type =
    "button";

  addButton.className =
    "qb-add-answer";

  addButton.textContent =
    window.SchoolMonitorI18n.t("qb_57dd9c945083");

  addButton.setAttribute(
    "data-add-fill-alternative",
    ""
  );


  card.appendChild(
    header
  );

  card.appendChild(
    hint
  );

  card.appendChild(
    alternatives
  );

  card.appendChild(
    addButton
  );

  return card;
}


// ===================================================
// PREVIEW + GAP SETTINGS
// ===================================================

function renderFillGaps() {

  if (
    !fillGapsText
    ||
    !fillGapsPreview
    ||
    !fillGapsSettings
  ) {
    return;
  }

  const source =
    fillGapsText.value;

  const previousAlternatives =
    collectFillGapAlternatives();

  const gaps =
    parseFillGapsSource(
      source
    );


  // -----------------------------------------------
  // EMPTY
  // -----------------------------------------------

  if (gaps.length === 0) {

    fillGapsPreview.textContent =
      "";

    fillGapsSettings.innerHTML =
      "";

    if (
      fillGapsPreviewSection
    ) {
      fillGapsPreviewSection.hidden =
        true;
    }

    return;
  }


  // -----------------------------------------------
  // PREVIEW
  // -----------------------------------------------

  fillGapsPreview.textContent =
    "";

  let cursor = 0;

  gaps.forEach(
    (gap) => {

      const text =
        source.slice(
          cursor,
          gap.start
        );

      if (text) {
        fillGapsPreview.appendChild(
          document.createTextNode(
            text
          )
        );
      }


      const placeholder =
        document.createElement(
          "span"
        );

      placeholder.className =
        "qb-fill-preview__gap";

      placeholder.textContent =
        gap.id;

      fillGapsPreview.appendChild(
        placeholder
      );

      cursor =
        gap.end;
    }
  );


  const finalText =
    source.slice(
      cursor
    );

  if (finalText) {
    fillGapsPreview.appendChild(
      document.createTextNode(
        finalText
      )
    );
  }


  if (
    fillGapsPreviewSection
  ) {
    fillGapsPreviewSection.hidden =
      false;
  }


  // -----------------------------------------------
  // SETTINGS
  // -----------------------------------------------

  fillGapsSettings.innerHTML =
    "";

  gaps.forEach(
    (gap) => {

      fillGapsSettings.appendChild(
        createFillGapCard(
          gap,
          previousAlternatives
        )
      );

    }
  );
}


if (fillGapsText) {

  fillGapsText.addEventListener(
    "input",
    renderFillGaps
  );

  renderFillGaps();
}


// ===================================================
// GAP ALTERNATIVE EVENTS
// ===================================================

if (fillGapsSettings) {

  fillGapsSettings.addEventListener(
    "click",
    (event) => {

      const target =
        event.target;

      if (
        !(target instanceof Element)
      ) {
        return;
      }


      // ---------------------------------------------
      // ADD
      // ---------------------------------------------

      const addButton =
        target.closest(
          "[data-add-fill-alternative]"
        );

      if (addButton) {

        const card =
          addButton.closest(
            "[data-fill-gap-card]"
          );

        if (!card) {
          return;
        }

        const gapId =
          card.dataset.gapId;

        if (!gapId) {
          return;
        }

        const container =
          card.querySelector(
            "[data-fill-alternatives]"
          );

        if (!container) {
          return;
        }

        const row =
          createFillAlternativeRow(
            gapId
          );

        container.appendChild(
          row
        );

        const input =
          row.querySelector(
            "input"
          );

        if (input) {
          input.focus();
        }

        return;
      }


      // ---------------------------------------------
      // REMOVE
      // ---------------------------------------------

      const removeButton =
        target.closest(
          "[data-remove-fill-alternative]"
        );

      if (!removeButton) {
        return;
      }

      const row =
        removeButton.closest(
          ".qb-short-answer-row"
        );

      if (row) {
        row.remove();
      }

    }
  );
}


// ===================================================
// WORD BANK DYNAMIC ROWS
// ===================================================

function updateFillWordRows() {

  if (!fillWordBankContainer) {
    return;
  }

  const rows =
    fillWordBankContainer
      .querySelectorAll(
        "[data-fill-word-row]"
      );

  rows.forEach(
    (row) => {

      const removeButton =
        row.querySelector(
          "[data-remove-fill-word]"
        );

      if (!removeButton) {
        return;
      }

      const onlyOne =
        rows.length <= 1;

      removeButton.hidden =
        onlyOne;

      removeButton.disabled =
        onlyOne;

    }
  );
}


function createFillWordRow() {

  if (!fillWordBankContainer) {
    return;
  }

  const row =
    document.createElement(
      "div"
    );

  row.className =
    "qb-short-answer-row";

  row.setAttribute(
    "data-fill-word-row",
    ""
  );


  const input =
    document.createElement(
      "input"
    );

  input.type =
    "text";

  input.name =
    "fill_word_bank";

  input.className =
    "qb-form-control";

  input.placeholder =
    window.SchoolMonitorI18n.t("qb_907aaa49ca43");

  input.setAttribute(
    "data-type-input",
    ""
  );

  input.disabled =
    !questionType
    ||
    questionType.value
      !== "fill_gaps"
    ||
    getFillGapsMode()
      !== "word_bank";


  const removeButton =
    document.createElement(
      "button"
    );

  removeButton.type =
    "button";

  removeButton.className =
    "qb-remove-answer";

  removeButton.textContent =
    "×";

  removeButton.setAttribute(
    "data-remove-fill-word",
    ""
  );

  removeButton.setAttribute(
    "aria-label",
    window.SchoolMonitorI18n.t("qb_1d7673a283cb")
  );


  row.appendChild(
    input
  );

  row.appendChild(
    removeButton
  );

  fillWordBankContainer
    .appendChild(
      row
    );

  updateFillWordRows();

  input.focus();
}


if (addFillWordButton) {

  addFillWordButton.addEventListener(
    "click",
    createFillWordRow
  );
}


if (fillWordBankContainer) {

  fillWordBankContainer.addEventListener(
    "click",
    (event) => {

      const target =
        event.target;

      if (
        !(target instanceof Element)
      ) {
        return;
      }

      const removeButton =
        target.closest(
          "[data-remove-fill-word]"
        );

      if (!removeButton) {
        return;
      }

      const rows =
        fillWordBankContainer
          .querySelectorAll(
            "[data-fill-word-row]"
          );

      if (rows.length <= 1) {
        return;
      }

      const row =
        removeButton.closest(
          "[data-fill-word-row]"
        );

      if (row) {
        row.remove();
      }

      updateFillWordRows();

    }
  );
}


updateFillWordRows();
updateFillGapsMode();

      // ===================================================
      // FORM VALIDATION
      // ===================================================

      const questionForm =
        document.querySelector(
          ".qb-question-form"
        );


      // IMAGE_CHOICE uses the same authenticated upload/view endpoints as the condition.
      const imageGroup = document.getElementById('image-choice-fields');
      function showImageCard(card) {
        const key = card.querySelector('[data-image-key]').value;
        const image = card.querySelector('[data-image-preview]');
        image.hidden = !key;
        card.querySelector('[data-image-placeholder]').hidden = !!key;
        if (key) {
          image.src = `${imageGroup.dataset.viewUrl}?object_key=${encodeURIComponent(key)}`;
          image.alt = card.querySelector('[data-image-alt]').value || window.SchoolMonitorI18n.t("qb_40c04cf94a1d", {p0: (card.dataset.imageCard)});
        } else image.removeAttribute('src');
      }
      if (imageGroup) {
        imageGroup.querySelectorAll('[data-image-card]').forEach(card => {
          const fileInput = card.querySelector('[data-image-file]');
          const status = card.querySelector('[data-image-status]');
          const clear = card.querySelector('[data-image-clear]');
          card.querySelector('[data-image-alt]').addEventListener('input', () => showImageCard(card));
          clear.addEventListener('click', () => {
            if (card.dataset.uploading === 'true') return;
            card.querySelector('[data-image-key]').value = '';
            fileInput.value = ''; fileInput.setCustomValidity(''); status.textContent = '';
            showImageCard(card);
          });
          fileInput.addEventListener('change', async () => {
            const file = fileInput.files[0];
            if (!file || card.dataset.uploading === 'true') return;
            fileInput.setCustomValidity('');
            if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
              status.textContent = window.SchoolMonitorI18n.t("qb_67f844532c6c");
              fileInput.value = ''; return;
            }
            card.dataset.uploading = 'true'; clear.disabled = true; fileInput.disabled = true;
            status.textContent = window.SchoolMonitorI18n.t("qb_87eb5bc52e82");
            try {
              const body = new FormData(); body.append('file', file);
              const response = await fetch(imageGroup.dataset.uploadUrl, {method:'POST', body, credentials:'same-origin'});
              const result = await response.json();
              if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : window.SchoolMonitorI18n.t("qb_ccf3f32dffcd"));
              if (typeof result.object_key !== 'string' || !/^question-bank\/media\/[1-9][0-9]*\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(result.object_key)) {
                throw new Error(window.SchoolMonitorI18n.t("qb_4052e3cf2080"));
              }
              card.querySelector('[data-image-key]').value = result.object_key;
              showImageCard(card); status.textContent = window.SchoolMonitorI18n.t("qb_c809021bf497");
            } catch (error) {
              status.textContent = error.message || window.SchoolMonitorI18n.t("qb_ccf3f32dffcd");
            } finally {
              card.dataset.uploading = 'false'; clear.disabled = false; fileInput.value = '';
              fileInput.disabled = questionType?.value !== 'image_choice';
            }
          });
        });
        questionForm?.addEventListener('submit', event => {
          if (questionType?.value !== 'image_choice') return;
          const cards = [...imageGroup.querySelectorAll('[data-image-card]')];
          if (cards.some(card => card.dataset.uploading === 'true')) {
            event.preventDefault();
            cards.filter(card => card.dataset.uploading === 'true').forEach(card => {
              card.querySelector('[data-image-status]').textContent = window.SchoolMonitorI18n.t("qb_e6ccd34f1bae");
            });
            return;
          }
          cards.forEach(card => card.querySelector('[data-image-file]').setCustomValidity(
            card.querySelector('[data-image-key]').value ? '' : window.SchoolMonitorI18n.t("qb_9d2094354f2f", {p0: (card.dataset.imageCard)})));
          if (!questionForm.checkValidity()) { event.preventDefault(); questionForm.reportValidity(); }
        });
      }

      const manualGroup = document.getElementById('manual-review-fields');
      if (manualGroup) {
        addManualCriterion();
        manualGroup.querySelector('[data-manual-add]').addEventListener('click', () => addManualCriterion());
        manualGroup.addEventListener('input', updateManualTotal);
        document.getElementById('max_score')?.addEventListener('input', updateManualTotal);
        questionType?.addEventListener('change', updateManualTotal);
        questionForm?.addEventListener('submit', event => {
          if (questionType?.value !== 'manual_review') return;
          updateManualTotal();
          if (!questionForm.checkValidity()) { event.preventDefault(); questionForm.reportValidity(); }
        });
      }

      const formulaGroup = document.getElementById('formula-fields');
      if (formulaGroup) {
        addFormulaMeaningRow();
        formulaGroup.querySelector('[data-formula-variable-add]').addEventListener('click', () => addFormulaMeaningRow());
        formulaGroup.querySelector('[data-formula-distractor-add]').addEventListener('click', () => addFormulaDistractor());
        questionForm?.addEventListener('submit', event => {
          if (questionType?.value !== 'formula' || formulaGroup.dataset.formulaPartsActive === 'true') return;
          const symbolInputs = [...formulaGroup.querySelectorAll('[name="formula_symbol"]')];
          symbolInputs.forEach(input => input.setCustomValidity(''));
          const seen = new Set();
          for (const input of symbolInputs) {
            const symbol = input.value.trim();
            if (!symbol || seen.has(symbol)) input.setCustomValidity(window.SchoolMonitorI18n.t("qb_d7ca2ea8ff5e"));
            seen.add(symbol);
          }
          const target = formulaGroup.querySelector('[name="formula_target_variable"]');
          target.setCustomValidity(target.value.trim() && !seen.has(target.value.trim())
            ? window.SchoolMonitorI18n.t("qb_e1b0b8585ac9") : '');
          if (!questionForm.checkValidity()) { event.preventDefault(); questionForm.reportValidity(); }
        });
        formulaGroup.addEventListener('input', event => event.target.setCustomValidity?.(''));
      }

      // Restore only once. Switching type never reapplies the original item.
      const initialNode = document.getElementById("qb-initial-item");
      if (initialNode && questionForm) {
        try {
          const initial = JSON.parse(initialNode.dataset.initialItem);
          const content = initial.content;
          const key = initial.answer_key;
          const type = initial.question_type;
          const group = document.querySelector(`[data-question-fields="${type}"]`);
          const set = (name, value) => {
            const input = group.querySelector(`[name="${name}"]`);
            if (input) input.value = value ?? "";
          };
          const select = (name, values) => {
            group.querySelectorAll(`[name="${name}"]`).forEach(input => {
              input.checked = values.includes(input.value);
            });
          };
          const text = segments => segments.map(s => s.text || "").join("");
          const rows = (container, selector, values, add, names) => {
            while (container.querySelectorAll(selector).length < values.length) add();
            const existing = [...container.querySelectorAll(selector)];
            existing.forEach((row, index) => {
              if (index >= values.length) { row.remove(); return; }
              names.forEach((name, field) => {
                row.querySelector(`[name="${name}"]`).value = values[index][field];
              });
            });
          };
          document.getElementById("qb-initial-grading").value = JSON.stringify(initial.grading_settings);
          document.getElementById("qb-initial-content").value = JSON.stringify(content);
          switch (type) {
            case "image_choice": {
              if (!Array.isArray(content.options) || content.options.length !== 4 ||
                  !["A", "B", "C", "D"].every(value => content.options.filter(option => option.value === value).length === 1) ||
                  !["A", "B", "C", "D"].includes(key.value)) throw new Error('Invalid image options');
              for (const option of content.options) {
                if (typeof option.object_key !== 'string' || !/^question-bank\/media\/[1-9][0-9]*\/[0-9a-f]{32}\.(png|jpg|webp)$/.test(option.object_key)) {
                  throw new Error('Invalid image key');
                }
                set(`image_option_${option.value.toLowerCase()}_key`, option.object_key);
                set(`image_option_${option.value.toLowerCase()}_alt`, option.alt || '');
                showImageCard(group.querySelector(`[data-image-card="${option.value}"]`));
              }
              select('image_correct_answer', [key.value]);
              break;
            }
            case "formula": {
              if (initial.grading_settings?.formula_score_policy === 'per_part_v1') {
                if (!Array.isArray(content.parts) || !key.parts || typeof key.parts !== 'object') throw new Error('Invalid formula parts');
                break; // formula_parts_editor.js restores each rich part and key.
              }
              const expression = key.expression ?? key.latex;
              if (typeof expression !== 'string' || !expression.trim()) throw new Error('Invalid formula answer');
              set('formula_answer', expression);
              group.querySelector('[name="formula_answer"]').dispatchEvent(new Event('input', {bubbles:true}));
              set('formula_target_variable', content.target_variable || '');
              const variables = content.variables || [];
              const options = content.meaning_options || [];
              const meanings = key.variable_meanings || {};
              if (!Array.isArray(variables) || variables.length > 30 || !Array.isArray(options) || options.length > 50) {
                throw new Error('Invalid formula meanings');
              }
              const optionMap = new Map(options.map(option => [option.value, option.label]));
              group.querySelector('[data-formula-variables]').replaceChildren();
              if (variables.length) {
                for (const symbol of variables) {
                  const label = meanings[symbol] ? optionMap.get(meanings[symbol]) : '';
                  if (meanings[symbol] && typeof label !== 'string') throw new Error('Missing variable meaning');
                  addFormulaMeaningRow(symbol, label || '');
                }
              } else addFormulaMeaningRow();
              group.querySelector('[data-formula-distractors]').replaceChildren();
              const correctIds = new Set(Object.values(meanings));
              const distractors = options.filter(option => !correctIds.has(option.value));
              if (distractors.length > 20) throw new Error('Too many formula distractors');
              distractors.forEach(option => addFormulaDistractor(option.label));

              break;
            }
            case "manual_review": {
              const criteria = initial.grading_settings.criteria;
              if (!Array.isArray(criteria) || !criteria.length || criteria.length > 50 ||
                  new Set(criteria.map(c => c?.id)).size !== criteria.length ||
                  criteria.some(c => !c || !/^C[1-9][0-9]*$/.test(c.id) ||
                    typeof c.title !== 'string' || typeof c.description !== 'string' ||
                    typeof c.max_score !== 'number' || !Number.isFinite(c.max_score) || c.max_score <= 0)) {
                throw new Error('Invalid manual review criteria');
              }
              manualGroup.querySelector('[data-manual-criteria]').replaceChildren();
              criteria.forEach(criterion => addManualCriterion(criterion));
              break;
            }
            case "single_choice":
            case "multiple_choice": {
              if (type==='single_choice' && Array.isArray(content.parts)) break;
              if (content.options.length !== 4 ||
                  !["A", "B", "C", "D"].every(v => content.options.some(o => o.value === v))) {
                throw new Error("This builder requires four options A–D");
              }
              for (const option of content.options) {
                const input = group.querySelector(`[name="option_${option.value.toLowerCase()}_segments"]`);
                if (input) {
                  input.closest("[data-rich-editor]").dataset.initialSegments = JSON.stringify(option.segments);
                } else {
                  const name = `option_${option.value.toLowerCase()}`;
                  const plain = group.querySelector(`[name="${name}"]`);
                  if (!plain) throw new Error("Missing option editor");
                  plain.value = text(option.segments);
                  const format = option.segments.length === 1 && option.segments[0].type === "latex" ? "latex" : "text";
                  select(`${name}_format`, [format]);
                  const hidden = document.createElement("input");
                  hidden.type = "hidden"; hidden.name = `${name}_segments`;
                  hidden.setAttribute("data-type-input", "");
                  plain.parentElement.appendChild(hidden);
                  const sync = () => {
                    const selected = group.querySelector(`[name="${name}_format"]:checked`)?.value || "text";
                    hidden.value = JSON.stringify(plain.value === text(option.segments) && selected === format
                      ? option.segments : [{type: selected, text: plain.value}]);
                  };
                  plain.addEventListener("input", sync);
                  group.querySelectorAll(`[name="${name}_format"]`).forEach(radio => radio.addEventListener("change", sync));
                  questionForm.addEventListener("submit", sync, true);
                  sync();
                }
              }
              select(type === "single_choice" ? "correct_answer" : "correct_answers",
                     type === "single_choice" ? [key.value] : key.values);
              break;
            }
            case "true_false": select("correct_answer", [String(key.value)]); break;
            case "short_text":
              rows(acceptedAnswersContainer, "[data-accepted-answer-row]",
                   key.accepted_answers.map(v => [v]), createAcceptedAnswerRow, ["accepted_answers"]);
              updateAcceptedAnswerRows();
              break;
            case "number":
              set("number_answer", key.value);
              set("number_unit", content.unit);
              set("number_tolerance", initial.grading_settings.tolerance);
              break;
            case "matching": {
              const left = new Map(content.left.map(v => [v.value, v]));
              const right = new Map(content.right.map(v => [v.value, v]));
              const values = key.pairs.map(p => [left.get(p.left), right.get(p.right)]);
              rows(matchingPairsContainer, "[data-matching-row]",
                   values.map(pair => pair.map(v => text(v.segments))), createMatchingRow,
                   ["matching_left", "matching_right"]);
              [...matchingPairsContainer.querySelectorAll("[data-matching-row]")].forEach((row, i) => {
                ["matching_left", "matching_right"].forEach((name, side) => {
                  const hidden = document.createElement("input");
                  hidden.type = "hidden"; hidden.name = `${name}_original_segments`;
                  hidden.value = JSON.stringify(values[i][side].segments);
                  hidden.setAttribute("data-type-input", ""); row.appendChild(hidden);
                });
              });
              updateMatchingRows(); break;
            }
            case "ordering": {
              const items = new Map(content.items.map(v => [v.value, v]));
              const values = key.order.map(v => items.get(v));
              rows(orderingItemsContainer, "[data-ordering-row]",
                   values.map(v => [text(v.segments)]), createOrderingRow, ["ordering_item"]);
              [...orderingItemsContainer.querySelectorAll("[data-ordering-row]")].forEach((row, i) => {
                const hidden = document.createElement("input");
                hidden.type = "hidden"; hidden.name = "ordering_item_original_segments";
                hidden.value = JSON.stringify(values[i].segments);
                hidden.setAttribute("data-type-input", ""); row.appendChild(hidden);
              });
              updateOrderingRows(); break;
            }
            case "fill_gaps": {
              select("fill_gaps_mode", [content.input_mode]);
              let index = 0;
              const gapIds = [];
              fillGapsText.value = content.segments.map(segment => {
                if (segment.type === "text") return segment.text;
                if (segment.type !== "gap") throw new Error("Unsupported fill-gaps segment");
                gapIds.push(segment.gap_id);
                const answer = key.gaps[segment.gap_id].accepted_answers[0];
                if (answer.includes("[[") || answer.includes("]]")) throw new Error("Unrepresentable gap answer");
                return `[[${answer}]]`;
              }).join("");
              if (parseFillGapsSource(fillGapsText.value).length !== gapIds.length) {
                throw new Error("Unrepresentable fill-gaps text");
              }
              renderFillGaps();
              for (const card of fillGapsSettings.querySelectorAll("[data-fill-gap-card]")) {
                const answers = key.gaps[gapIds[index++]].accepted_answers.slice(1);
                const list = card.querySelector("[data-fill-alternatives]");
                answers.forEach(answer => list.appendChild(createFillAlternativeRow(card.dataset.gapId, answer)));
              }
              const correct = new Set(Object.values(key.gaps).flatMap(v => v.accepted_answers));
              const extra = (content.word_bank || []).filter(v => !correct.has(v));
              rows(fillWordBankContainer, "[data-fill-word-row]", (extra.length ? extra : [""]).map(v => [v]),
                   createFillWordRow, ["fill_word_bank"]);
              updateFillWordRows(); updateFillGapsMode(); break;
            }
            default: throw new Error("Unsupported question type");
          }
          const alignOriginals = () => {
            for (const [container, rowSelector, names] of [
              [matchingPairsContainer, "[data-matching-row]", ["matching_left", "matching_right"]],
              [orderingItemsContainer, "[data-ordering-row]", ["ordering_item"]]
            ]) {
              if (!container) continue;
              container.querySelectorAll(rowSelector).forEach(row => names.forEach(name => {
                if (row.querySelector(`[name="${name}_original_segments"]`)) return;
                const hidden = document.createElement("input");
                hidden.type = "hidden"; hidden.name = `${name}_original_segments`; hidden.value = "";
                hidden.setAttribute("data-type-input", "");
                hidden.disabled = questionType.value !== container.closest("[data-question-fields]").dataset.questionFields;
                row.appendChild(hidden);
              }));
            }
          };
          questionForm.addEventListener("submit", alignOriginals, true);
          updateQuestionTypeFields();
          updateFillGapsMode();
          questionType.addEventListener("change", () => {
            document.getElementById("qb-initial-grading").disabled = questionType.value !== type;
            document.getElementById("qb-initial-content").disabled = questionType.value !== type;
          });
          document.activeElement?.blur();
        } catch (error) {
          console.error("Question hydration failed", error);
          const message = document.createElement("div");
          message.className = "qb-empty";
          message.textContent = window.SchoolMonitorI18n.t("qb_aa803691ed59");
          questionForm.prepend(message);
          questionForm.querySelectorAll('[type="submit"]').forEach(button => button.disabled = true);
          questionForm.addEventListener("submit", event => event.preventDefault());
        }
      }

      updateQuestionTypeFields();
      updateFillGapsMode();

      if (questionForm) {

        questionForm.addEventListener(
          "submit",
          (event) => {

            if (!questionType) {
              return;
            }


            // =============================================
            // MULTIPLE CHOICE
            // =============================================

            if (
              questionType.value
              === "multiple_choice"
            ) {

              const multipleChoiceGroup =
                document.getElementById(
                  "multiple-choice-fields"
                );

              if (!multipleChoiceGroup) {
                return;
              }

              const checkedAnswers =
                multipleChoiceGroup
                  .querySelectorAll(
                    'input[name="correct_answers"]:checked'
                  );

              if (
                checkedAnswers.length === 0
              ) {

                event.preventDefault();

                const firstCheckbox =
                  multipleChoiceGroup
                    .querySelector(
                      'input[name="correct_answers"]'
                    );

                if (firstCheckbox) {

                  firstCheckbox
                    .setCustomValidity(
                      window.SchoolMonitorI18n.t("qb_e0d2b1d4c7fc")
                    );

                  firstCheckbox
                    .reportValidity();

                  firstCheckbox
                    .setCustomValidity(
                      ""
                    );
                }

                return;
              }
            }


            // =============================================
            // SHORT TEXT
            // =============================================

            if (
              questionType.value
              === "short_text"
            ) {

              const shortTextGroup =
                document.getElementById(
                  "short-text-fields"
                );

              if (!shortTextGroup) {
                return;
              }

              const answerInputs =
                shortTextGroup
                  .querySelectorAll(
                    'input[name="accepted_answers"]:not(:disabled)'
                  );

              const hasAnswer =
                Array.from(
                  answerInputs
                ).some(
                  (input) =>
                    input.value.trim() !== ""
                );

              if (!hasAnswer) {

                event.preventDefault();

                const firstAnswer =
                  answerInputs[0];

                if (firstAnswer) {

                  firstAnswer
                    .setCustomValidity(
                      window.SchoolMonitorI18n.t("qb_bd6b012cb626")
                    );

                  firstAnswer
                    .reportValidity();

                  firstAnswer
                    .setCustomValidity(
                      ""
                    );
                }

                return;
              }
            }


            // =============================================
            // NUMBER
            // =============================================

            if (
              questionType.value
              === "number"
            ) {

              const toleranceInput =
                document.getElementById(
                  "number_tolerance"
                );

              if (
                toleranceInput
                &&
                !toleranceInput.disabled
                &&
                toleranceInput.value.trim()
                  !== ""
              ) {

                const normalizedTolerance =
                  toleranceInput.value
                    .trim()
                    .replace(
                      ",",
                      "."
                    );

                const tolerance =
                  Number(
                    normalizedTolerance
                  );

                if (
                  !Number.isFinite(
                    tolerance
                  )
                  ||
                  tolerance < 0
                ) {

                  event.preventDefault();

                  toleranceInput
                    .setCustomValidity(
                      window.SchoolMonitorI18n.t("qb_6f6f620b97db")
                    );

                  toleranceInput
                    .reportValidity();

                  toleranceInput
                    .setCustomValidity(
                      ""
                    );

                  return;
                }
              }
            }

            // =============================================
            // FILL GAPS
            // =============================================

            if (
            questionType.value
            === "fill_gaps"
            ) {

              if (!fillGapsText) {
                return;
              }

              const gaps =
                parseFillGapsSource(
                fillGapsText.value
                );

              if (gaps.length === 0) {

                event.preventDefault();

                fillGapsText.setCustomValidity(
                  window.SchoolMonitorI18n.t("qb_a3206d1de6cb")
                );

                fillGapsText.reportValidity();

                fillGapsText.setCustomValidity(
                ""
                );

                return;
              }


              const hasEmptyGap =
                gaps.some(
                (gap) =>
                  !gap.answer.trim()
                );

              if (hasEmptyGap) {

                event.preventDefault();

                fillGapsText.setCustomValidity(
                  window.SchoolMonitorI18n.t("qb_818193dd0364")
                );

                fillGapsText.reportValidity();

                fillGapsText.setCustomValidity(
                  ""
                );

                return;
              }
            }

          }
        );
      }

    }
  );

/* Always-visible visual preview, including legacy AI LaTeX saved as prose.
 * Display only: never rewrites hidden payloads or correct-answer values. */
(() => {
  function startVisualPreviews() {
    document.querySelectorAll('[data-rich-editor]').forEach(editor => {
      const content = editor.querySelector('[data-rich-content], .qb-rich-editor__content');
      if (!content || editor.querySelector('[data-qb-visual-preview]')) return;
      const panel = document.createElement('div');
      panel.dataset.qbVisualPreview = '';
      panel.style.cssText = 'margin-top:12px;padding:12px 14px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;color:#0f172a;overflow-wrap:anywhere;';
      const title = document.createElement('div');
      title.textContent = window.SchoolMonitorI18n.t("qb_ab81129bf498");
      title.style.cssText = 'font:600 13px/1.5 system-ui;margin-bottom:8px;color:#475569;';
      const body = document.createElement('div');
      body.style.cssText = 'font:400 16px/1.6 system-ui;white-space:pre-wrap;';
      panel.append(title, body); editor.append(panel);
      function math(source) {
        const field = document.createElement('math-field');
        field.setAttribute('read-only', ''); field.setAttribute('math-virtual-keyboard-policy', 'manual');
        field.tabIndex = -1; field.textContent = source;
        field.style.cssText = 'display:inline-block;max-width:100%;vertical-align:middle;border:0;background:transparent;font-size:1.15em;pointer-events:none;';
        body.append(field);
      }
      function prose(value) {
        // Explicit delimiters, or an ASCII math expression containing a LaTeX
        // command. Cyrillic/Kazakh prose cannot be swallowed by this fallback.
        const pattern = /\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]|([A-Za-z0-9_{}^=+*/().<>|,:;!\-]*\\[A-Za-z]+(?:\{[^\n]*?\}|[A-Za-z0-9_{}^=+*/().<>|,:;!\\\-])*)/g;
        let offset = 0;
        for (const match of value.matchAll(pattern)) {
          body.append(document.createTextNode(value.slice(offset, match.index)));
          math(match[1] ?? match[2] ?? match[3] ?? match[4]);
          offset = match.index + match[0].length;
        }
        body.append(document.createTextNode(value.slice(offset)));
      }
      function walk(node) {
        if (node.nodeType === Node.TEXT_NODE) { prose(node.textContent); return; }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (node.matches('[data-rich-math]')) { math(node.dataset.latex || node.textContent); return; }
        if (node.matches('math-field')) { math(node.value || node.textContent); return; }
        if (node.tagName === 'IMG') {
          const img = document.createElement('img'); img.src = node.src; img.alt = node.alt;
          img.style.cssText = 'max-width:100%;max-height:220px;object-fit:contain;'; body.append(img); return;
        }
        if (node.tagName === 'BR') { body.append(document.createTextNode('\n')); return; }
        node.childNodes.forEach(walk);
        if (node !== content && /^(DIV|P)$/.test(node.tagName)) body.append(document.createTextNode('\n'));
      }
      function render() { body.replaceChildren(); walk(content); panel.hidden = !content.textContent.trim() && !content.querySelector('img'); }
      render();
      content.addEventListener('input', render);
      new MutationObserver(render).observe(content, { childList:true, subtree:true, characterData:true, attributes:true, attributeFilter:['data-latex','src'] });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(startVisualPreviews, 0));
  else setTimeout(startVisualPreviews, 0);
})();
