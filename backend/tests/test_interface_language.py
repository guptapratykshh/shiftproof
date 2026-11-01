import copy
import pytest
from shiftproof import service
from shiftproof.engine import question_intent, answer_question
from test_handover import add

@pytest.mark.parametrize('text,intent',[
    ('क्या बाकी है?', 'pending'), ('क्या बदला है?', 'changes'),
    ('इस पर रोक क्यों है?', 'hold'), ('इस बैच पर रोक क्यों है?', 'hold'),
])
def test_interface_hindi_questions_are_supported(text, intent):
    assert question_intent(text) == intent


def test_localizable_answers_preserve_sources_and_state(repo):
    add(repo, 'packing-hold')
    before = copy.deepcopy(repo.load())
    answer = answer_question(before, 'B-17', 'इस पर रोक क्यों है?')
    assert answer['intent'] == 'hold'
    assert answer['items']
    for item in answer['items']:
        assert item['note_ids']
        assert all(note_id in before['notes'] for note_id in item['note_ids'])
        assert item['presentation']['type'] in ('task', 'reason')
    history = answer_question(before, 'B-17', 'क्या बदला है?')
    for item in history['items']:
        claim = before['claims'][item['claim_ids'][0]]
        assert item['presentation']['value'] == claim['value']
        assert item['presentation']['property'] == claim['property']
    assert before == repo.load()
