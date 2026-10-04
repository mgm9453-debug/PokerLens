import sys
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def sample():
    path = Path(__file__).parent / 'fixtures' / '持牌座位匿名.png'
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def test_six_opponents_and_folded_lower_left():
    from vision.player_detector import PlayerDetector
    result = PlayerDetector().detect(sample())
    assert result.reliable
    assert result.active_seats == (2, 3, 4, 5, 6, 7)


def test_scaled_table_preserves_seats():
    from vision.player_detector import PlayerDetector
    frame = cv2.resize(sample(), (846, 599))
    result = PlayerDetector().detect(frame)
    assert result.reliable
    assert result.active_seats == (2, 3, 4, 5, 6, 7)


def test_missing_seat_is_unknown_not_folded():
    from vision.player_detector import PlayerDetector
    frame = sample()
    frame[357:412, 72:132] = 0
    result = PlayerDetector().detect(frame)
    assert not result.reliable
    assert result.active_seats == ()


def test_blank_screen_cannot_assume_all_active():
    from vision.player_detector import PlayerDetector
    result = PlayerDetector().detect(np.zeros((799, 1128, 3), np.uint8))
    assert not result.reliable
    assert result.active_seats == ()
def test_faceup_rectangle_is_not_assumed_folded():
    import cv2
    import numpy as np
    from pathlib import Path
    from vision.player_detector import PlayerDetector,SEAT_REGIONS
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/持牌座位匿名.png',np.uint8),1)
    h,w=frame.shape[:2]
    x,y,rw,rh=SEAT_REGIONS[2]
    frame[round(y*h):round((y+rh)*h),round(x*w):round((x+rw)*w)]=245
    detection=PlayerDetector().detect(frame)
    assert not detection.reliable
    assert '攤牌' in detection.reason

def test_current_green_card_backs_count_three_opponents():
    import cv2
    import numpy as np
    from pathlib import Path
    from vision.player_detector import PlayerDetector
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/green_backs_anonymous.png',np.uint8),1)
    result=PlayerDetector().detect(frame)
    assert result.reliable,result.reason
    assert result.active_seats==(2,5,6)

def test_green_only_ignores_empty_seats_and_dark_avatars():
    from vision.player_detector import PlayerDetector,SEAT_REGIONS
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/green_backs_anonymous.png',np.uint8),1)
    h,w=frame.shape[:2]
    for seat in (1,3,4,7):
        x,y,rw,rh=SEAT_REGIONS[seat]
        frame[round(y*h):round((y+rh)*h),round(x*w):round((x+rw*1.9)*w)]=35
    result=PlayerDetector(green_only=True).detect(frame)
    assert result.reliable,result.reason
    assert result.active_seats==(2,5,6)

def test_green_only_rejects_uniform_green_background():
    from vision.player_detector import PlayerDetector
    result=PlayerDetector(green_only=True).detect(np.full((799,1128,3),(70,130,80),np.uint8))
    assert not result.reliable
    assert not result.active_seats



def test_green_avatar_letters_do_not_block_player_count():
    from vision.player_detector import PlayerDetector,SEAT_REGIONS
    frame=np.full((799,1128,3),35,np.uint8)
    x,y,w,h=SEAT_REGIONS[2]
    crop=frame[round(y*799):round((y+h)*799),round(x*1128):round((x+w)*1128)]
    for start in (3,17,31,45):
        cv2.rectangle(crop,(start,3),(start+5,48),(60,190,70),-1)
    result=PlayerDetector(green_only=True).detect(frame)
    assert result.reliable,result.reason
    assert result.active_seats==()


def test_shifted_green_back_is_found_by_its_emblem():
    from vision.player_detector import PlayerDetector,SEAT_REGIONS
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/green_backs_anonymous.png',np.uint8),1)
    x,y,w,h=SEAT_REGIONS[2]
    left,top=round(x*1128),round(y*799)
    original=frame[top:top+55,left:left+60].copy()
    frame[top:top+55,left:left+60]=35
    frame[top+4:top+59,left+12:left+72]=original
    result=PlayerDetector(green_only=True).detect(frame)
    assert result.reliable,result.reason
    assert result.active_seats==(2,5,6)


def test_green_rectangle_without_card_emblem_is_not_a_player():
    from vision.player_detector import PlayerDetector,SEAT_REGIONS
    frame=np.full((799,1128,3),35,np.uint8)
    x,y,w,h=SEAT_REGIONS[2]
    crop=frame[round(y*799):round((y+h)*799),round(x*1128):round((x+w)*1128)]
    crop[:]=(65,140,80)
    crop[::6,:]=(100,180,100)
    result=PlayerDetector(green_only=True).detect(frame)
    assert not result.reliable
    assert not result.active_seats


def test_small_green_table_keeps_correct_active_seats():
    from vision.player_detector import PlayerDetector
    frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'fixtures/green_backs_anonymous.png',np.uint8),1)
    result=PlayerDetector(green_only=True).detect(cv2.resize(frame,(564,400)))
    assert result.reliable,result.reason
    assert result.active_seats==(2,5,6)


def test_smooth_green_felt_without_border_does_not_block():
    from vision.player_detector import PlayerDetector,SEAT_REGIONS
    frame=np.full((799,1128,3),35,np.uint8)
    x,y,w,h=SEAT_REGIONS[2]
    crop=frame[round(y*799):round((y+h)*799),round(x*1128):round((x+w)*1128)]
    for row in range(crop.shape[0]):crop[row,:]=(50+row//3,100+row,60+row//3)
    result=PlayerDetector(green_only=True).detect(frame)
    assert result.reliable,result.reason
    assert not result.active_seats
