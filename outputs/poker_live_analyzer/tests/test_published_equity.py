import pytest
from poker.published_equity import published_reference, matchup_equity, load_tables
from poker.starting_hands import starting_hand_guide


def test_public_dataset_coverage_and_known_values():
    table, matrix = load_tables()
    assert len(table) == len(matrix['classes']) == 169
    assert published_reference(['Ts', 'Th'])['random_equity'] == pytest.approx(.75)
    assert published_reference(['Qs', 'Ks'])['random_equity'] == pytest.approx(.634)
    assert matchup_equity('AA', 'KK') > .80
    assert matchup_equity('KK', 'AA') == pytest.approx(1-matchup_equity('AA', 'KK'))
    assert matchup_equity('AKs', 'AKs') == pytest.approx(.5)


def test_only_complete_heads_up_preflop_ranges_are_supported():
    ref = published_reference(['As', 'Kh'], opponent_ranges=['標準'])
    assert 0 < ref['range_equity'] < 1
    assert ref['range_combos'] > 0
    assert '平手' in ref['label']
    assert 'range_equity' not in published_reference(['As', 'Kh'], opponent_ranges=['標準', '標準'])
    assert 'range_equity' not in published_reference(['As', 'Kh'], opponent_ranges=[[['Qs', 'Qh']]])
    assert not published_reference(['As', 'Kh'], board=['2c', '3c', '4d'])


def test_reference_is_added_without_changing_user_chart():
    guide = starting_hand_guide(['Ts', 'Th'])
    assert guide['published_reference']['random_equity'] == pytest.approx(.75)
    assert guide['entry_chart']['color'] == '藍色'
    assert guide['published_reference']['strategy_available'] is False


def test_invalid_cards_and_hand_classes_are_rejected():
    with pytest.raises(ValueError):
        published_reference(['As', 'As'])
    with pytest.raises(ValueError):
        matchup_equity('AK', 'QQ')


def test_all_matchups_have_valid_complements():
    _, matrix = load_tables()
    for a in matrix['classes']:
        for b in matrix['classes']:
            assert 0 <= matchup_equity(a, b) <= 1
            assert matchup_equity(a, b)+matchup_equity(b, a) == pytest.approx(1)


def test_missing_data_preserves_existing_guide(monkeypatch):
    import poker.published_equity as module
    def unavailable():
        raise OSError('測試資料不可用')
    monkeypatch.setattr(module, 'load_tables', unavailable)
    guide = starting_hand_guide(['Ts', 'Th'])
    assert not guide['published_reference']
    assert guide['entry_chart']['color'] == '藍色'


@pytest.mark.parametrize('hero,opponent', [(['As','Ah'],'KK'), (['Ks','Qs'],'標準'), (['7s','2h'],'AA')])
def test_public_reference_agrees_with_independent_simulation(hero, opponent):
    from poker.equity import calculate_equity
    estimate = calculate_equity(hero, [], [opponent], iterations=10000, seed=2718)
    reference = published_reference(hero, opponent_ranges=[opponent])
    assert reference['range_equity'] == pytest.approx(estimate.hero_equity, abs=.03)


def test_corrupted_resource_is_rejected(monkeypatch, tmp_path):
    import poker.published_equity as module
    module.load_tables.cache_clear()
    (tmp_path/'starting-hands-vs-random.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(module, 'resource_path', lambda relative: tmp_path)
    with pytest.raises(ValueError, match='完整性'):
        module.load_tables()
    assert not module.optional_reference(['As','Ah'])
    module.load_tables.cache_clear()
