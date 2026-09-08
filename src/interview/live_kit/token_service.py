import os
from livekit import api


def create_candidate_token(
    room_name: str = "interview-room",
    candidate_id: str = "candidate-1",
    candidate_name: str = "Candidate",
) -> str:
    """
    Generates an audio-only JWT access token for the candidate to connect via WebRTC.
    Uses local dev credentials (devkey/secret) by default if not specified in .env.
    """
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(candidate_id)
        .with_name(candidate_name)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_publish_sources=["microphone"],  # Audio only (No Camera / Screen Share)
                can_subscribe=True,
                can_publish_data=True,
            )
        )
    )
    return token.to_jwt()


if __name__ == "__main__":
    jwt = create_candidate_token()
    print("\n[Generated Candidate Audio Token]:")
    print(jwt)
