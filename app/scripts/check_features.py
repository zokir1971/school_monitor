"""Read-only check before starting a local test or restricted release."""
import argparse
from app.core.feature_flags import get_features

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect',required=True,choices=['enabled','restricted'])
    args=parser.parse_args();flags=get_features()
    print('ASSESSMENT_ENABLED='+str(flags.ASSESSMENT_ENABLED).lower())
    print('SCHOOL_EDUCATION_ENABLED='+str(flags.SCHOOL_EDUCATION_ENABLED).lower())
    expected=args.expect=='enabled'
    if (flags.ASSESSMENT_ENABLED,flags.SCHOOL_EDUCATION_ENABLED)!=(expected,expected):
        print('Feature settings do not match the requested mode.');return 2
    print('Feature settings OK. No database connection made.');return 0

if __name__=='__main__':raise SystemExit(main())
