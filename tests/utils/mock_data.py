"""Shared mock data for unit and integration tests."""

SAMPLE_TEXT_EN = (
    "My name is John Smith and my email is john.smith@example.com. "
    "My phone number is +1-555-867-5309 and my SSN is 123-45-6789."
)

SAMPLE_TEXT_PT = (
    "Meu CPF é 123.456.789-09 e o CNPJ da empresa é 12.345.678/0001-90."
)

SAMPLE_TEXT_WITH_AADHAAR = (
    "Aadhaar: 2345 6789 0123, PAN: ABCDE1234F"
)

SAMPLE_REDACTED_TEXT = (
    "My name is <PERSON> and my email is <EMAIL_ADDRESS>. "
    "My phone number is <PHONE_NUMBER> and my SSN is <US_SSN>."
)

MOCK_ENTITY_COUNTS = {
    "PERSON": 1,
    "EMAIL_ADDRESS": 1,
    "PHONE_NUMBER": 1,
    "US_SSN": 1,
}

MOCK_ENTITIES_FOUND = [
    {"type": "PERSON",        "start": 11, "end": 21, "score": 0.85, "original": "John Smith"},
    {"type": "EMAIL_ADDRESS", "start": 37, "end": 59, "score": 1.0,  "original": "john.smith@example.com"},
    {"type": "PHONE_NUMBER",  "start": 75, "end": 90, "score": 0.75, "original": "+1-555-867-5309"},
    {"type": "US_SSN",        "start": 103, "end": 114, "score": 0.85, "original": "123-45-6789"},
]

MOCK_PROCESS_RESULT = {
    "redacted_text":    SAMPLE_REDACTED_TEXT,
    "entities_found":   MOCK_ENTITIES_FOUND,
    "entity_counts":    MOCK_ENTITY_COUNTS,
    "detected_language": "en",
}

SAMPLE_TXT_BYTES = SAMPLE_TEXT_EN.encode("utf-8")

SAMPLE_CSV_BYTES = b"name,email\nJohn Smith,john@example.com\nJane Doe,jane@example.com"
