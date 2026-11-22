from copy import deepcopy
from app.modules.reports.rules.notebook_criteria import CHECKING_NOTEBOOKS_CRITERIA, CHECKING_NOTEBOOKS_RATING

CHECKING_NOTEBOOKS_SYSTEM_SCHEMA = {
    'version': 3,
    'criteria': deepcopy(CHECKING_NOTEBOOKS_CRITERIA),
    'score_scale': [0, 1, 2],
    'rating': deepcopy(CHECKING_NOTEBOOKS_RATING),
}
