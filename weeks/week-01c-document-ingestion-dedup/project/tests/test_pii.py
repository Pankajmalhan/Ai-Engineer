from app.pii import PresidioPIIRedactor, RegexPIIRedactor
from tests.conftest import requires_presidio

TEXT = (
    "Please contact Priya Chen at priya.chen@example.com or 415-555-0199 "
    "regarding employee ID EM-482913."
)


def test_regex_redactor_finds_email_phone_and_id():
    matches = RegexPIIRedactor().find(TEXT)
    entity_types = {m.entity_type for m in matches}
    assert "EMAIL_ADDRESS" in entity_types
    assert "PHONE_NUMBER" in entity_types
    assert "ID_NUMBER" in entity_types


def test_regex_redactor_replaces_matches_with_entity_tags():
    redacted, matches = RegexPIIRedactor().redact(TEXT)
    assert "priya.chen@example.com" not in redacted
    assert "415-555-0199" not in redacted
    assert "EM-482913" not in redacted
    assert "<EMAIL_ADDRESS>" in redacted
    assert "<PHONE_NUMBER>" in redacted
    assert "<ID_NUMBER>" in redacted
    assert len(matches) == 3


def test_regex_redactor_finds_nothing_in_clean_text():
    matches = RegexPIIRedactor().find("The refund window is thirty days.")
    assert matches == []


@requires_presidio
def test_presidio_redactor_finds_person_entity_regex_cannot():
    matches = PresidioPIIRedactor().find(TEXT)
    entity_types = {m.entity_type for m in matches}
    assert "PERSON" in entity_types
    assert "EMAIL_ADDRESS" in entity_types


@requires_presidio
def test_presidio_redactor_redacts_all_detected_entities():
    redacted, matches = PresidioPIIRedactor().redact(TEXT)
    assert "Priya Chen" not in redacted
    assert "priya.chen@example.com" not in redacted
    assert len(matches) >= 2


@requires_presidio
def test_presidio_custom_id_recognizer_catches_employee_id():
    matches = PresidioPIIRedactor().find("Employee ID EM-482913 was reviewed.")
    assert any(m.entity_type == "ID_NUMBER" and "EM-482913" in m.text for m in matches)
