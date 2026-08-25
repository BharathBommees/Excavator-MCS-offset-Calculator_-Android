"""
Custom Kivy widgets for the Excavator Offset Calculator (Android build).

Diagrams are drawn natively with Kivy canvas instructions (Line, Ellipse,
Color) rather than embedding matplotlib. matplotlib has no official,
reliable python-for-android recipe and is a common source of Android
build failures / huge APK size, so native Kivy drawing is used instead
for portability and a much smaller, more reliable build.
"""

import math
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Line, Ellipse
from kivy.properties import ListProperty
from kivy.core.text import LabelBase


POINT_COLORS = {
    "origin": (0.1, 0.1, 0.1, 1),
    "primary": (0.85, 0.1, 0.1, 1),
    "secondary": (0.1, 0.3, 0.85, 1),
    "bp_port": (0.15, 0.7, 0.3, 1),
    "bp_stbd": (0.15, 0.7, 0.3, 1),
    "bucket": (0.95, 0.6, 0.05, 1),
    "c1": (0.55, 0.1, 0.75, 1),
}


def fit_transform(points, widget_size, margin_frac=0.14):
    """
    Given a list of (x, y) data points and the target widget (w, h) in
    pixels, return a function data_to_px(x, y) -> (px, py) that maps data
    coordinates into widget-local pixel coordinates, preserving aspect
    ratio and leaving a margin. Y is NOT flipped (Kivy's origin is
    bottom-left, matching a standard math/plan-view Y-up convention).
    """
    w, h = widget_size
    if w <= 1 or h <= 1 or not points:
        return lambda x, y: (w / 2.0, h / 2.0)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = xmax - xmin
    dy = ymax - ymin
    if dx < 1e-9:
        dx = 1.0
    if dy < 1e-9:
        dy = 1.0

    margin_x = w * margin_frac
    margin_y = h * margin_frac
    avail_w = max(w - 2 * margin_x, 1.0)
    avail_h = max(h - 2 * margin_y, 1.0)

    scale = min(avail_w / dx, avail_h / dy)
    cx_data = (xmin + xmax) / 2.0
    cy_data = (ymin + ymax) / 2.0
    cx_px = w / 2.0
    cy_px = h / 2.0

    def data_to_px(x, y):
        return (float(cx_px + (x - cx_data) * scale), float(cy_px + (y - cy_data) * scale))

    return data_to_px


class BaseDiagram(Widget):
    """Common scaffolding: holds data, redraws on size change."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._data = None
        self._labels = []
        self.bind(size=self._redraw, pos=self._redraw)

    def clear_labels(self):
        for lbl in self._labels:
            self.remove_widget(lbl)
        self._labels = []

    def abs_pt(self, local_pt):
        """Canvas graphics (Line/Ellipse) need ABSOLUTE window coordinates,
        unlike child widgets which Kivy positions relative to the parent
        automatically. This offsets a widget-local (x, y) point by the
        widget's own screen position."""
        return (local_pt[0] + self.x, local_pt[1] + self.y)

    def add_label(self, text, px, py, color=(0, 0, 0, 1), bold=True, font_size=13,
                  halign="left", offset=(6, 6)):
        lbl = Label(
            text=text, color=color, bold=bold, font_size=font_size,
            size_hint=(None, None), halign=halign, valign="middle",
        )
        lbl.texture_update()
        lbl.size = lbl.texture_size
        lbl.pos = (self.x + px + offset[0], self.y + py + offset[1])
        self.add_widget(lbl)
        self._labels.append(lbl)
        return lbl

    def set_data(self, data):
        self._data = data
        self._redraw()

    def _redraw(self, *args):
        raise NotImplementedError


class PlanViewDiagram(BaseDiagram):
    """Top-down plan view in raw survey (world) coordinates."""

    def _redraw(self, *args):
        self.canvas.clear()
        self.clear_labels()
        r = self._data
        if not r:
            with self.canvas:
                Color(0.5, 0.5, 0.5, 1)
            self.add_label("No data yet - calculate on tab 2", self.width / 2 - 90,
                            self.height / 2, bold=False)
            return

        rp = r["raw_points"]
        o = r["origin"]
        have_bucket = r["have_bucket"]

        pts_world = {
            "origin": (o[0], o[1]),
            "primary": (rp["P"][0], rp["P"][1]),
            "secondary": (rp["S"][0], rp["S"][1]),
            "bp_port": (rp["BPp"][0], rp["BPp"][1]),
            "bp_stbd": (rp["BPs"][0], rp["BPs"][1]),
        }
        if have_bucket:
            pts_world["bucket"] = (rp["Bk"][0], rp["Bk"][1])

        # synthetic reference ray endpoint if no bucket
        if not have_bucket:
            ray_len = max(r["baseline_dist"], 0.5) * 2.0
            theta = math.radians(r["ref_heading"])
            ref_x = o[0] + ray_len * math.sin(theta)
            ref_y = o[1] + ray_len * math.cos(theta)
        else:
            ref_x, ref_y = pts_world["bucket"]

        all_pts = list(pts_world.values()) + [(ref_x, ref_y)]
        t = fit_transform(all_pts, self.size)

        def T(key):
            return self.abs_pt(t(*pts_world[key]))

        with self.canvas:
            # boom pin baseline
            Color(0.15, 0.7, 0.3, 1)
            a = T("bp_port"); b = T("bp_stbd")
            Line(points=[a[0], a[1], b[0], b[1]], width=1.3, dash_length=6, dash_offset=3)

            # antenna baseline
            Color(0.1, 0.3, 0.85, 1)
            a = T("primary"); b = T("secondary")
            Line(points=[a[0], a[1], b[0], b[1]], width=1.6)

            # reference heading line
            Color(0.95, 0.55, 0.05, 1)
            ox, oy = T("origin")
            rx, ry = self.abs_pt(t(ref_x, ref_y))
            Line(points=[ox, oy, rx, ry], width=1.8, dash_length=8, dash_offset=4)

            # faint origin->antenna connectors
            Color(0.5, 0.5, 0.5, 0.6)
            px_, py_ = T("primary")
            Line(points=[ox, oy, px_, py_], width=1.0)
            sx_, sy_ = T("secondary")
            Line(points=[ox, oy, sx_, sy_], width=1.0)

            # points
            for key, (x, y) in pts_world.items():
                px, py = self.abs_pt(t(x, y))
                Color(*POINT_COLORS[key])
                r_dot = 6
                Ellipse(pos=(px - r_dot, py - r_dot), size=(r_dot * 2, r_dot * 2))

        labels = {
            "origin": "Origin\n(Boom Pin Ctr)", "primary": "Primary Ant",
            "secondary": "Secondary Ant", "bp_port": "BoomPin Port",
            "bp_stbd": "BoomPin Stbd", "bucket": "Bucket Ctr",
        }
        for key, (x, y) in pts_world.items():
            px, py = t(x, y)  # add_label already offsets by self.x/self.y itself
            self.add_label(labels[key], px, py, color=(0.05, 0.05, 0.05, 1), font_size=12)

        ox_l, oy_l = t(*pts_world["origin"])
        rx_l, ry_l = t(ref_x, ref_y)
        mid_x, mid_y = (ox_l + rx_l) / 2.0, (oy_l + ry_l) / 2.0
        self.add_label(f"Heading offset = {r['heading_offset']:+.2f} deg",
                        mid_x, mid_y - 20, color=(0.55, 0.1, 0.6, 1), font_size=13,
                        offset=(-40, 0))


class AngleConstructionDiagram(BaseDiagram):
    """Close-up of the Law-of-Cosines construction in the tilt-corrected
    local (Right, Fwd) plane -- shows exactly where the angle is measured."""

    def _redraw(self, *args):
        self.canvas.clear()
        self.clear_labels()
        r = self._data
        if not r:
            with self.canvas:
                Color(0.5, 0.5, 0.5, 1)
            self.add_label("No data yet - calculate on tab 2", self.width / 2 - 90,
                            self.height / 2, bold=False)
            return

        P2 = r["loc_P2"]; S2 = r["loc_S2"]; C1 = r["loc_C1"]
        line_a = r["loc_line_pt_a"]; line_b = r["loc_line_pt_b"]

        d0 = line_b - line_a
        length = max(float((d0[0] ** 2 + d0[1] ** 2) ** 0.5), 1e-6)
        dirn = (d0[0] / length, d0[1] / length)
        margin = max(length, r["loc_Da"], r["loc_Db"]) * 0.9
        mid = ((line_a[0] + line_b[0]) / 2.0, (line_a[1] + line_b[1]) / 2.0)
        ref_p1 = (mid[0] - dirn[0] * margin, mid[1] - dirn[1] * margin)
        ref_p2 = (mid[0] + dirn[0] * margin, mid[1] + dirn[1] * margin)

        all_pts = [tuple(P2), tuple(S2), tuple(C1), ref_p1, ref_p2]
        t = fit_transform(all_pts, self.size)

        with self.canvas:
            # reference line
            Color(0.15, 0.7, 0.3, 1)
            a = self.abs_pt(t(*ref_p1)); b = self.abs_pt(t(*ref_p2))
            Line(points=[a[0], a[1], b[0], b[1]], width=1.2, dash_length=4, dash_offset=3)

            # Da: Primary -> Secondary
            Color(0.1, 0.3, 0.85, 1)
            p = self.abs_pt(t(*P2)); s = self.abs_pt(t(*S2))
            Line(points=[p[0], p[1], s[0], s[1]], width=2.2)

            # Db: Primary -> C1
            Color(0.55, 0.1, 0.75, 1)
            c1 = self.abs_pt(t(*C1))
            Line(points=[p[0], p[1], c1[0], c1[1]], width=2.2, dash_length=6, dash_offset=3)

            # Dc: Secondary -> C1
            Color(0.5, 0.5, 0.5, 1)
            Line(points=[s[0], s[1], c1[0], c1[1]], width=1.0, dash_length=3, dash_offset=2)

            # angle arc at Primary
            vec1 = (S2[0] - P2[0], S2[1] - P2[1])
            vec2 = (C1[0] - P2[0], C1[1] - P2[1])
            ang1 = math.degrees(math.atan2(vec1[1], vec1[0]))
            ang2 = math.degrees(math.atan2(vec2[1], vec2[0]))
            diff = (ang2 - ang1 + 180.0) % 360.0 - 180.0
            radius_data = 0.35 * min(r["loc_Da"], r["loc_Db"])
            arc_pts = []
            n = 30
            for i in range(n + 1):
                frac = i / n
                theta = math.radians(ang1 + diff * frac)
                ax = P2[0] + radius_data * math.cos(theta)
                ay = P2[1] + radius_data * math.sin(theta)
                pxa, pya = self.abs_pt(t(ax, ay))
                arc_pts += [pxa, pya]
            Color(0.95, 0.55, 0.05, 1)
            Line(points=arc_pts, width=2.4)

            # points
            Color(*POINT_COLORS["primary"])
            r_dot = 7
            Ellipse(pos=(p[0] - r_dot, p[1] - r_dot), size=(r_dot * 2, r_dot * 2))
            Color(*POINT_COLORS["secondary"])
            Ellipse(pos=(s[0] - r_dot, s[1] - r_dot), size=(r_dot * 2, r_dot * 2))
            Color(*POINT_COLORS["c1"])
            r_dot2 = 6
            Ellipse(pos=(c1[0] - r_dot2, c1[1] - r_dot2), size=(r_dot2 * 2, r_dot2 * 2))

        # local (non-offset) coords for labels -- add_label offsets by
        # self.x/self.y itself, so it must receive LOCAL coordinates.
        p_l = t(*P2); s_l = t(*S2); c1_l = t(*C1)
        self.add_label("Primary\n(angle here)", p_l[0], p_l[1], color=(0.7, 0.05, 0.05, 1), font_size=12)
        self.add_label("Secondary", s_l[0], s_l[1], color=(0.05, 0.15, 0.6, 1), font_size=12)
        self.add_label("C1 (foot of\nperpendicular)", c1_l[0], c1_l[1] - 30,
                        color=(0.4, 0.05, 0.55, 1), font_size=11)

        mid_t = math.radians(ang1 + diff * 0.5)
        radius_data = 0.35 * min(r["loc_Da"], r["loc_Db"]) * 1.6
        label_x = P2[0] + radius_data * math.cos(mid_t)
        label_y = P2[1] + radius_data * math.sin(mid_t)
        lx, ly = t(label_x, label_y)
        self.add_label(f"{r['heading_offset']:.2f} deg", lx, ly, color=(0.85, 0.45, 0.0, 1),
                        font_size=14, offset=(-25, 0))


class GridHeadingDiagram(BaseDiagram):
    """Tab 4: simple two-point plan view for the GPS rover cross-check."""

    def _redraw(self, *args):
        self.canvas.clear()
        self.clear_labels()
        v = self._data
        if not v:
            with self.canvas:
                Color(0.5, 0.5, 0.5, 1)
            self.add_label("No data yet", self.width / 2 - 40, self.height / 2, bold=False)
            return

        A = v["gps_aft"]; B = v["gps_bucket"]
        t = fit_transform([tuple(A), tuple(B)], self.size)
        a = t(*A); b = t(*B)  # local coords, used for labels
        a_abs = self.abs_pt(a); b_abs = self.abs_pt(b)

        with self.canvas:
            Color(0.95, 0.55, 0.05, 1)
            Line(points=[a_abs[0], a_abs[1], b_abs[0], b_abs[1]], width=1.8, dash_length=8, dash_offset=4)
            Color(*POINT_COLORS["bp_port"])
            r_dot = 7
            Ellipse(pos=(a_abs[0] - r_dot, a_abs[1] - r_dot), size=(r_dot * 2, r_dot * 2))
            Color(*POINT_COLORS["bucket"])
            Ellipse(pos=(b_abs[0] - r_dot, b_abs[1] - r_dot), size=(r_dot * 2, r_dot * 2))

        self.add_label("Aft / Centerline Pt", a[0], a[1], color=(0.1, 0.5, 0.2, 1), font_size=12)
        self.add_label("Bucket Ctr", b[0], b[1], color=(0.75, 0.45, 0.0, 1), font_size=12)

        mid_x, mid_y = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        self.add_label(
            f"Grid heading = {v['grid_heading']:.2f} deg\nResidual = {v['residual']:+.2f} deg",
            mid_x, mid_y - 30, color=(0.55, 0.1, 0.6, 1), font_size=12, offset=(-60, 0),
        )


# ----------------------------------------------------------------------
# Highlighted results panel (true yellow background per line, matching
# the desktop app's Text-widget tag highlighting)
# ----------------------------------------------------------------------
class HighlightLine(BoxLayout):
    def __init__(self, text, highlight=False, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, padding=(4, 2), **kwargs)
        self.label = Label(
            text=text, markup=False, halign="left", valign="middle",
            size_hint_y=None, font_size=13,
            color=(0, 0, 0, 1) if highlight else (0.92, 0.92, 0.92, 1),
        )
        self.label.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self.label.bind(texture_size=self._update_height)
        self.add_widget(self.label)
        self.highlight = highlight
        with self.canvas.before:
            self._color = Color(1, 0.96, 0.55, 1) if highlight else Color(0, 0, 0, 0)
            from kivy.graphics import Rectangle
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _update_height(self, instance, size):
        instance.height = size[1] + 6
        self.height = instance.height


class ResultsPanel(ScrollView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=1, padding=(4, 4))
        self.layout.bind(minimum_height=self.layout.setter("height"))
        self.add_widget(self.layout)

    def set_lines(self, lines):
        """lines: list of (text, highlight_bool) tuples."""
        self.layout.clear_widgets()
        for text, hl in lines:
            self.layout.add_widget(HighlightLine(text, highlight=hl))

    def set_message(self, text):
        self.set_lines([(text, False)])
