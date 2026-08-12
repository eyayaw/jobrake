"""Endpoint, app key, and headers for Indeed's mobile-app GraphQL API."""

from __future__ import annotations

API_URL = "https://apis.indeed.com/graphql"

# The public API key baked into Indeed's iOS app—shared by every client of
# this endpoint (jobspy ships the same one), so it is not a secret. If Indeed
# rotates it, requests start failing with 401/403; lift the fresh key from the
# app or jobspy and update this one line.
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
