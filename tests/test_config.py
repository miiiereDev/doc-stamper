from autostamper.config import StampConfig


def test_valid_default():
    c = StampConfig()
    assert c.is_valid()
    assert c.target_page == "last"
    assert not c.is_locked
    assert not c.keep_aspect


def test_invalid_rel():
    c = StampConfig(rel_x=0.9, rel_w=0.2)
    assert not c.is_valid()
    c = StampConfig(rel_y=0.9, rel_h=0.2)
    assert not c.is_valid()
    c = StampConfig(rel_w=0)
    assert not c.is_valid()


def test_tolerance_not_locked():
    c = StampConfig(is_locked=False, std_width=612, std_height=792)
    assert not c.violates_tolerance(1000, 1000)


def test_tolerance_locked():
    c = StampConfig(is_locked=True, std_width=612, std_height=792, tolerance=3.0)
    assert not c.violates_tolerance(612, 792)
    assert not c.violates_tolerance(615, 792)
    assert c.violates_tolerance(616, 792)
    assert c.violates_tolerance(612, 796)
    assert c.violates_tolerance(500, 500)


def test_label():
    c = StampConfig(is_locked=False)
    assert c.label() == "Standard: Not Set"
    c.is_locked = True
    c.std_width = 595
    c.std_height = 842
    assert "595.0" in c.label() and "Locked" in c.label()


def test_keep_aspect_flag():
    c = StampConfig(keep_aspect=True)
    assert c.keep_aspect
    c.keep_aspect = False
    assert not c.keep_aspect
