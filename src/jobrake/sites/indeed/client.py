"""Endpoint and headers for Indeed's mobile-app GraphQL API."""

API_URL = "https://apis.indeed.com/graphql"

# Indeed ships this public key in its iOS app, taken from jobspy.
# If changed, 401/403 results will be returned.
INDEED_APP_KEY = "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"

API_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": INDEED_APP_KEY,
    "accept": "application/json",
    "indeed-locale": "en-US",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15"
        " (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

__all__ = ["API_HEADERS", "API_URL", "INDEED_APP_KEY"]
