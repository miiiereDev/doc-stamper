from dataclasses import dataclass


@dataclass
class StampConfig:
    std_width: float = 0.0
    std_height: float = 0.0
    rel_x: float = 0.1
    rel_y: float = 0.1
    rel_w: float = 0.2
    rel_h: float = 0.15
    target_page: str = "last"
    tolerance: float = 3.0
    is_locked: bool = False
    keep_aspect: bool = True
    rotation: float = 0.0
    rotation_snap_90: bool = False

    def is_valid(self) -> bool:
        return (
            0.0 <= self.rel_x <= 1.0
            and 0.0 <= self.rel_y <= 1.0
            and 0.0 < self.rel_w <= 1.0
            and 0.0 < self.rel_h <= 1.0
            and self.rel_x + self.rel_w <= 1.0
            and self.rel_y + self.rel_h <= 1.0
            and self.target_page in ("first", "last")
            and 0.0 <= self.rotation < 360.0
        )

    def normalize_rotation(self):
        self.rotation = self.rotation % 360.0
        if self.rotation_snap_90:
            self.rotation = round(self.rotation / 90.0) * 90.0 % 360.0

    def violates_tolerance(self, w: float, h: float) -> bool:
        if not self.is_locked:
            return False
        return abs(w - self.std_width) > self.tolerance or abs(h - self.std_height) > self.tolerance

    def label(self) -> str:
        if not self.is_locked:
            return "Standard: Not Set"
        return f"Standard: {self.std_width:.1f} x {self.std_height:.1f} pt (Locked)"
