import numpy as np
import pytest


def test_rank_classifier_recognizes_template_and_rejects_blank():
    from vision.card_classifier import CardClassifier
    classifier = CardClassifier()
    for rank in '23456789TJQKA':
        mask = classifier.example(rank)
        result = classifier.classify(mask * 255)
        assert result.rank == rank
        assert result.confidence >= 0.85
    assert classifier.classify(np.zeros((40, 30), np.uint8)) is None


def test_stability_requires_three_matching_frames():
    from vision.card_detector import Detection, StableCards
    stable = StableCards()
    detection = Detection(('Ad','8d'), (), .95, True)
    assert stable.update(detection) is None
    assert stable.update(detection) is None
    assert stable.update(detection) == detection
    assert stable.update(detection) is None


def test_uncertainty_resets_stability_and_duplicates_rejected():
    from vision.card_detector import Detection, StableCards
    stable = StableCards()
    assert stable.update(Detection(('Ad','8d'), (), .95, True)) is None
    assert stable.update(Detection(('Ad','8d'), (), .7, False)) is None
    assert stable.update(Detection(('Ad','8d'), (), .95, True)) is None
    with pytest.raises(ValueError):
        Detection(('Ad','Ad'), (), .99, True)


def test_no_cards_are_waiting_not_fake_results():
    from vision.card_detector import CardDetector
    detection = CardDetector().detect(np.zeros((800, 1128, 3), np.uint8))
    assert detection.hero == ()
    assert detection.board == ()


def test_visible_board_distinguishes_black_clubs_from_spades():
    import cv2
    from pathlib import Path
    from vision.card_detector import CardDetector
    frame = cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/board_anonymous.png', np.uint8), 1)
    detection = CardDetector().detect(frame)
    assert detection.reliable
    assert detection.board == ('Ks','4s','5c','8c')
