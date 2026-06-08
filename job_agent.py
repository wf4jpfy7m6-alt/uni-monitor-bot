import requests

url = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "X-API-Key": "jobboerse-jobsuche"
}

params = {
    "was": "Reinigungskraft",
    "wo": "Wilhelmshaven",
    "umkreis": 40
}

try:
    r = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    print("STATUS:")
    print(r.status_code)

    print("BODY:")
    print(r.text[:2000])

except Exception as e:
    print("ERROR:")
    print(str(e))
