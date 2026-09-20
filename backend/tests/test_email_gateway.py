import subprocess
import sys
from pathlib import Path


def test_development_gateway_builds_multipart_alternative_and_rejects_crlf():
    code = """
from app.services.lifecycle_service import DevelopmentEmailGateway, EmailDeliveryError

gateway = DevelopmentEmailGateway()
message = gateway.build_message(
    'maya@example.test',
    'Appointment confirmed',
    'Plain meaning',
    '<html><body><p>Plain meaning</p></body></html>',
)
assert message.get_content_type() == 'multipart/alternative'
assert message.get_body(preferencelist=('plain',)).get_content().strip() == 'Plain meaning'
assert '<p>Plain meaning</p>' in message.get_body(preferencelist=('html',)).get_content()
try:
    gateway.build_message(
        'maya@example.test',
        'Safe subject\\r\\nBcc: attacker@example.test',
        'Plain',
        '<p>Plain</p>',
    )
except EmailDeliveryError:
    pass
else:
    raise AssertionError('CR/LF subject was accepted')
try:
    gateway.build_message(
        'maya@example.test\\nBcc: attacker@example.test',
        'Safe subject',
        'Plain',
        '<p>Plain</p>',
    )
except EmailDeliveryError:
    pass
else:
    raise AssertionError('CR/LF recipient was accepted')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr
