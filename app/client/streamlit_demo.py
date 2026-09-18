"""Local Streamlit UI for the Cloud Operations Runbook Assistant demo.

Wraps the same code path as app/client/demo_client.py (Cognito auth +
direct HTTPS invoke of the deployed AgentCore Runtime) behind a form, so an
audience sees the structured, grounded investigation result rendered as
sections instead of scrolling terminal text.

This is a local dev-server UI only - it reads terraform outputs and calls
AWS with the operator's own AWS_PROFILE credentials, so it must not be
exposed beyond localhost or published as a public link.

Usage:
    export AWS_PROFILE=mahidevops
    streamlit run app/client/streamlit_demo.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import streamlit as st

from app.client.auth import get_access_token
from app.client.demo_client import invoke

REPO_ROOT = Path(__file__).resolve().parents[2]
TF_DIR = REPO_ROOT / "terraform"


@st.cache_resource(show_spinner="Reading terraform outputs...")
def load_deployment_config() -> dict:
    result = subprocess.run(
        ["terraform", f"-chdir={TF_DIR}", "output", "-json"],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = json.loads(result.stdout)
    return {key: value["value"] for key, value in raw.items()}


def render_result(envelope: dict) -> None:
    result = envelope["result"]

    col1, col2 = st.columns(2)
    col1.metric("Correlation ID", envelope["correlation_id"])
    col2.metric("Client-observed latency", f"{envelope['client_observed_latency_seconds']}s")

    if result.get("refused"):
        st.error(f"**Refused:** {result.get('refusal_reason')}")
        return

    st.caption(f"Simulated evidence used: {result.get('simulated_evidence_used')}")

    st.subheader("Observations")
    observations = result.get("observations", [])
    if observations:
        st.table(
            [{"Fact": obs["fact"], "Source tool": obs["source_tool"]} for obs in observations]
        )
    else:
        st.write("_None reported._")

    st.subheader("Possible causes")
    for cause in result.get("possible_causes", []):
        st.markdown(f"- {cause}")

    st.subheader("Recommendations")
    for rec in result.get("recommendations", []):
        st.markdown(f"- {rec}")

    if result.get("assumptions"):
        st.subheader("Assumptions")
        for assumption in result["assumptions"]:
            st.markdown(f"- {assumption}")

    st.subheader("Citations")
    citations = result.get("citations", [])
    if citations:
        for citation in citations:
            st.markdown(f"- {citation}")
    else:
        st.write("_No applicable runbook found._")


def main() -> None:
    st.set_page_config(page_title="Cloud Operations Runbook Assistant", layout="wide")
    st.title("Cloud Operations Runbook Assistant")
    st.caption(
        "Grounded incident investigation over approved runbooks and operational evidence, "
        "via AgentCore Runtime + Gateway + Bedrock Knowledge Base."
    )

    config = load_deployment_config()

    with st.sidebar:
        st.header("Caller identity")
        user_id = st.selectbox("User", config["demo_user_ids"])
        st.caption(
            "demo-incident-commander can read + write; "
            "demo-read-only-operator can only read internal/public runbooks."
        )
        dashboard_url = (
            f"https://{config['aws_region']}.console.aws.amazon.com/cloudwatch/home"
            f"?region={config['aws_region']}#dashboards:name={config['dashboard_name']}"
        )
        st.link_button("Open observability dashboard", dashboard_url)

    with st.form("investigation_form"):
        incident_description = st.text_area(
            "Incident description",
            value=(
                "The production checkout service is returning HTTP 5xx errors. "
                "Help me investigate using the approved runbook."
            ),
            height=100,
        )
        col1, col2, col3 = st.columns(3)
        service = col1.text_input("Service", value="checkout")
        environment = col2.selectbox("Environment", ["production", "staging"])
        severity = col3.selectbox("Severity", ["SEV1", "SEV2", "SEV3", "SEV4"], index=1)
        submitted = st.form_submit_button("Investigate", type="primary")

    if submitted:
        with st.spinner(f"Authenticating as {user_id} and running the investigation..."):
            bearer_token = get_access_token(
                user_id=user_id,
                password=config["demo_user_passwords"][user_id],
                client_id=config["cognito_user_pool_client_id"],
                region=config["aws_region"],
            )
            envelope = invoke(
                agent_runtime_arn=config["agent_runtime_arn"],
                region=config["aws_region"],
                bearer_token=bearer_token,
                incident_description=incident_description,
                service=service,
                environment=environment,
                severity=severity,
            )
        render_result(envelope)


if __name__ == "__main__":
    main()
