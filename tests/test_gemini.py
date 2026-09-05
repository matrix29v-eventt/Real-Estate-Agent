from unittest.mock import Mock

import pytest
import requests

from services.llm_service import GeminiProvider, LLMCallError, LLMUnavailable, build_providers


def test_gemini_requires_key(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', '')
    provider = build_providers()[0]
    assert isinstance(provider, GeminiProvider)
    with pytest.raises(LLMUnavailable):
        provider.complete_json('system', 'user', {})


def test_gemini_structured_response(monkeypatch):
    response = Mock(status_code=200, ok=True)
    response.json.return_value = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
        {'text': 'private thought', 'thought': True}, {'text': '{"score": 70}'}
    ]}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, 'post', post)
    schema = {'type': 'object', 'properties': {'score': {'type': 'integer'}}}
    result = GeminiProvider(api_key='test-key').complete_json('system', 'user', schema)
    assert result == {'score': 70}
    request = post.call_args.kwargs
    assert request['headers']['x-goog-api-key'] == 'test-key'
    assert request['json']['generationConfig']['responseJsonSchema'] == schema
    assert request['json']['generationConfig']['thinkingConfig']['thinkingLevel'] == 'low'


@pytest.mark.parametrize('status,match', [(429, 'quota'), (403, 'rejected'), (503, 'HTTP 503')])
def test_gemini_http_errors(monkeypatch, status, match):
    monkeypatch.setattr(requests, 'post', Mock(return_value=Mock(status_code=status, ok=False)))
    with pytest.raises(LLMCallError, match=match):
        GeminiProvider(api_key='test-key').complete_json('system', 'user', {})


@pytest.mark.parametrize('payload', [
    {'promptFeedback': {'blockReason': 'SAFETY'}},
    {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': '{}'}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'invalid'}]}}]},
])
def test_gemini_rejects_unusable_answers(monkeypatch, payload):
    response = Mock(status_code=200, ok=True)
    response.json.return_value = payload
    monkeypatch.setattr(requests, 'post', Mock(return_value=response))
    with pytest.raises(LLMCallError):
        GeminiProvider(api_key='test-key').complete_json('system', 'user', {})


def test_gemini_timeout_does_not_expose_key(monkeypatch):
    monkeypatch.setattr(requests, 'post', Mock(side_effect=requests.Timeout('test-key')))
    with pytest.raises(LLMCallError, match='timed out') as error:
        GeminiProvider(api_key='test-key').complete_json('system', 'user', {})
    assert 'test-key' not in str(error.value)
