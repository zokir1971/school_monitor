"""Readable symbols for plain-text explanations; never touch expression contracts."""
import re

SYMBOLS = {'in': '∈', 'notin': '∉', 'ni': '∋', 'cap': '∩', 'cup': '∪', 'subset': '⊂', 'subseteq': '⊆', 'subsetneq': '⊊', 'supset': '⊃', 'supseteq': '⊇', 'emptyset': '∅', 'varnothing': '∅', 'le': '≤', 'leq': '≤', 'ge': '≥', 'geq': '≥', 'ne': '≠', 'neq': '≠', 'times': '×', 'cdot': '·', 'pm': '±', 'mp': '∓', 'infty': '∞', 'to': '→', 'rightarrow': '→', 'leftarrow': '←', 'leftrightarrow': '↔', 'Rightarrow': '⇒', 'Leftrightarrow': '⇔', 'forall': '∀', 'exists': '∃', 'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'theta': 'θ', 'lambda': 'λ', 'pi': 'π', 'sigma': 'σ', 'omega': 'ω', 'Delta': 'Δ', 'Sigma': 'Σ', 'Omega': 'Ω'}
_COMMAND = re.compile(r"(?<!\\)\\([A-Za-z]+)")


def readable_math_prose(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Пояснение должно быть строкой или None.")
    # Explicit math is author data; preserve LaTeX commands inside its delimiters.
    chunks=re.split(r'(\\\(.*?\\\)|\\\[.*?\\\])',value,flags=re.DOTALL)
    return ''.join(chunk if index%2 else _COMMAND.sub(lambda match: SYMBOLS.get(match.group(1),match.group(0)),chunk) for index,chunk in enumerate(chunks))
