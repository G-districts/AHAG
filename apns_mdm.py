import ssl
import json
import httpx

APNS_HOST = "https://api.push.apple.com"
APNS_TOPIC = "com.apple.mgmt.External.9507ef8f-dcbb-483e-89db-298d5471c6c1"
CERT_PATH = "certs/mdm_push.pem"


def send_mdm_push(device_token: str):
    payload = {"mdm": ""}  # MDM wake-only push

    ssl_context = ssl.create_default_context()
    ssl_context.load_cert_chain(CERT_PATH)

    with httpx.Client(http2=True, verify=ssl_context) as client:
        r = client.post(
            f"{APNS_HOST}/3/device/{device_token}",
            headers={
                "apns-topic": APNS_TOPIC,
                "apns-push-type": "mdm",
                "content-type": "application/json"
            },
            content=json.dumps(payload)
        )

    if r.status_code != 200:
        raise RuntimeError(f"APNs error {r.status_code}: {r.text}")
