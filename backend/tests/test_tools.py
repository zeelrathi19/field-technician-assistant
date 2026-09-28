import json

import pytest

from app.domain import ErrorCode
from app.tools import ARG_MODELS, ParsedCall, ToolDispatcher, tool_specs

d = ToolDispatcher()


@pytest.mark.parametrize("name,raw", [
    ("update_status", "{not json"),
    ("update_status", '{"status":"Completed"}'),
    ("update_status", '{"id":1,"status":"Completed"}'),
    ("update_status", '{"id":"WO-001","status":"Closed"}'),
    ("update_status", '{"id":"WO-001","status":"completed"}'),
    ("update_status", '{"id":"WO-001","status":"Completed","override":true}'),
    ("update_status", '{"id":"WO-001","id":"WO-003","status":"Completed"}'),
    ("update_status", '{"id":"wo-1","status":"Completed"}'),
    ("update_status", "[]"),
    ("add_note", '{"id":"WO-002","text":"   "}'),
    ("add_note", '{"id":"WO-002","text":"' + "x" * 2001 + '"}'),
    ("escalate", '{"id":"WO-006","reason":""}'),
    ("escalate", '{"id":"WO-006","reason":"' + "x" * 501 + '"}'),
    ("escalate", '{"id":"WO-006","reason":"a","actor":"tech-priya"}'),
    ("get_work_order", '{"id":"WO-001","n":NaN}'),
    ("get_work_order", '{"id":"WO-001","pad":"' + "x" * 9000 + '"}'),
    ("respond", '{"kind":"answer","text":"x","citations":[{"section_id":"kb-1","quote":"q","extra":1}],"missing":[]}'),
])
def test_malformed_arguments_rejected(name, raw):
    r = d.parse("c1", name, raw)
    assert not isinstance(r, ParsedCall)
    assert r.code == ErrorCode.INVALID_ARGUMENTS


@pytest.mark.parametrize("name", ["delete_work_order", "exec", "update_status ", "", "__import__"])
def test_unknown_tools_rejected(name):
    r = d.parse("c1", name, '{"id":"WO-001"}')
    assert r.code == ErrorCode.UNKNOWN_TOOL


def test_valid_calls_trim():
    r = d.parse("c1", "add_note", '{"id":" WO-002 ","text":"  filter replaced  "}')
    assert isinstance(r, ParsedCall) and r.args.id == "WO-002" and r.args.text == "filter replaced"
    assert r.is_mutation and r.target_id == "WO-002"


def test_dict_arguments_accepted():
    r = d.parse("c1", "get_work_order", {"id": "WO-001"})
    assert isinstance(r, ParsedCall) and not r.is_mutation


def test_specs_cover_exactly_registry_and_are_strict():
    specs = tool_specs()
    assert [s["name"] for s in specs] == list(ARG_MODELS)
    for s in specs:
        p = s["parameters"]
        assert p["additionalProperties"] is False and set(p["required"]) == set(p["properties"])


@pytest.mark.parametrize("spec", tool_specs(), ids=lambda s: s["name"])
def test_schema_properties_match_validator_fields(spec):
    model = ARG_MODELS[spec["name"]]
    assert set(spec["parameters"]["properties"]) == set(model.model_fields)
    json.dumps(spec)
