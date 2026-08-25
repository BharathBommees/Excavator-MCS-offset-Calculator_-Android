"""
Excavator GNSS Antenna & Boom-Pin Offset Calculator - Android (Kivy) build
============================================================================
Mobile port of the desktop (Tkinter) app. Same calculations
(core_logic.py, byte-for-byte identical formulas, validated against the
user's legacy calibration spreadsheet), rebuilt UI using Kivy so it can
be packaged into an Android APK with Buildozer.

Created by: Bharath Bommeeshwar Kumar
"""

import os
from kivy.config import Config
Config.set("kivy", "exit_on_escape", "0")

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.metrics import dp

import core_logic as cl
from custom_widgets import PlanViewDiagram, AngleConstructionDiagram, GridHeadingDiagram, ResultsPanel

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
REFERENCE_IMAGE = os.path.join(ASSETS_DIR, "excavator_reference_labeled.png")

HL_GOLD = (0.85, 0.65, 0.1, 1)


def show_error(title, message):
    popup = Popup(
        title=title,
        content=Label(text=message, halign="center"),
        size_hint=(0.85, 0.4),
    )
    popup.open()


# ----------------------------------------------------------------------
# Reusable small helpers
# ----------------------------------------------------------------------
def labeled_row(label_text, width_hint=0.4):
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6))
    lbl = Label(text=label_text, size_hint_x=width_hint, halign="left", valign="middle")
    lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
    row.add_widget(lbl)
    return row


class PointEntryRow(BoxLayout):
    """One row of X/Y/Z TextInputs for a named survey point."""

    def __init__(self, label_text, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(4), **kwargs)
        lbl = Label(text=label_text, size_hint_x=0.36, halign="left", valign="middle", font_size=12)
        lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(lbl)
        self.entries = {}
        for axis in ["x", "y", "z"]:
            ti = TextInput(multiline=False, input_filter="float", size_hint_x=0.213,
                            font_size=13, write_tab=False)
            self.entries[axis] = ti
            self.add_widget(ti)

    def get_point(self, required=True):
        vals = {}
        blanks = [a for a in ["x", "y", "z"] if self.entries[a].text.strip() == ""]
        if blanks and not required and len(blanks) == 3:
            return None
        for axis in ["x", "y", "z"]:
            raw = self.entries[axis].text.strip()
            if raw == "":
                if required:
                    raise ValueError(f"Missing {axis.upper()} value")
                return None
            try:
                vals[axis] = float(raw)
            except ValueError:
                raise ValueError(f"Invalid number for {axis.upper()}: '{raw}'")
        return vals

    def set_point(self, x, y, z):
        self.entries["x"].text = str(x)
        self.entries["y"].text = str(y)
        self.entries["z"].text = str(z)

    def clear(self):
        for e in self.entries.values():
            e.text = ""

    def set_enabled(self, enabled):
        for e in self.entries.values():
            e.disabled = not enabled


class PointEntryRow2D(BoxLayout):
    """X/Y-only entry row (used on tab 4, no elevation needed)."""

    def __init__(self, label_text, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(4), **kwargs)
        lbl = Label(text=label_text, size_hint_x=0.45, halign="left", valign="middle", font_size=12)
        lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(lbl)
        self.entries = {}
        for axis in ["x", "y"]:
            ti = TextInput(multiline=False, input_filter="float", size_hint_x=0.275,
                            font_size=13, write_tab=False)
            self.entries[axis] = ti
            self.add_widget(ti)

    def get_point(self):
        vals = {}
        for axis in ["x", "y"]:
            raw = self.entries[axis].text.strip()
            if raw == "":
                raise ValueError(f"Missing {axis.upper()} value")
            try:
                vals[axis] = float(raw)
            except ValueError:
                raise ValueError(f"Invalid number for {axis.upper()}: '{raw}'")
        return vals


# ----------------------------------------------------------------------
# Tab 1 - Reference / Terminology
# ----------------------------------------------------------------------
def build_reference_tab():
    root = ScrollView()
    box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(10), spacing=dp(8))
    box.bind(minimum_height=box.setter("height"))

    title = Label(
        text="Reference diagram - point/side naming convention used throughout this app:",
        size_hint_y=None, height=dp(50), bold=True, halign="left", valign="middle",
    )
    title.bind(size=lambda inst, val: setattr(inst, "text_size", val))
    box.add_widget(title)

    if os.path.exists(REFERENCE_IMAGE):
        img = Image(source=REFERENCE_IMAGE, size_hint_y=None, height=dp(280), allow_stretch=True,
                    keep_ratio=True)
        box.add_widget(img)

    legend_text = (
        "Port side = operator cabin side.  Starboard side = opposite side.\n\n"
        "Primary antenna = port-side, aft mast.  Secondary antenna = "
        "starboard-side mast.\n\n"
        "Boom Pin Port / Boom Pin Starboard = the two survey shots taken "
        "on either end of the boom foot pin; their midpoint is the "
        "machine origin (0,0,0).\n\n"
        "Bucket Center = center of the bucket teeth, used with the origin "
        "to define the true forward heading axis of the machine (when "
        "the 'With bucket center' method is selected)."
    )
    legend = Label(text=legend_text, size_hint_y=None, halign="left", valign="top", font_size=13)
    legend.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    legend.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1]))
    box.add_widget(legend)

    root.add_widget(box)
    return root


# ----------------------------------------------------------------------
# Tab 2 - Survey Input
# ----------------------------------------------------------------------
class InputTab(ScrollView):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(10), spacing=dp(8))
        box.bind(minimum_height=box.setter("height"))

        header = Label(
            text="Enter Total Station coordinates (X=Easting, Y=Northing, Z=Elevation), "
                 "same units for all points (e.g. meters):",
            size_hint_y=None, height=dp(60), halign="left", valign="middle", font_size=13,
        )
        header.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        box.add_widget(header)

        col_header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
        col_header.add_widget(Label(text="Point", size_hint_x=0.36, bold=True, font_size=12))
        for t in ["X", "Y", "Z"]:
            col_header.add_widget(Label(text=t, size_hint_x=0.213, bold=True, font_size=12))
        box.add_widget(col_header)

        self.point_rows = {}
        for key, label in cl.POINT_LABELS:
            row = PointEntryRow(label)
            self.point_rows[key] = row
            box.add_widget(row)

        # Heading reference method
        method_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(6))
        method_row.add_widget(Label(text="Heading method:", size_hint_x=0.4, font_size=13))
        self.method_spinner = Spinner(
            text="With bucket center",
            values=["With bucket center", "Without bucket center"],
            size_hint_x=0.6, font_size=13,
        )
        self.method_spinner.bind(text=self.on_method_change)
        method_row.add_widget(self.method_spinner)
        box.add_widget(method_row)

        self.bucket_hint = Label(
            text="Bucket Center is required for 'With bucket center'.",
            size_hint_y=None, height=dp(24), font_size=11, color=(0.6, 0.6, 0.6, 1),
            halign="left", valign="middle",
        )
        self.bucket_hint.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        box.add_widget(self.bucket_hint)

        sep = Label(text="", size_hint_y=None, height=dp(4))
        box.add_widget(sep)

        att_header = Label(
            text="Machine attitude at time of survey (digital level):",
            size_hint_y=None, height=dp(28), bold=True, halign="left", valign="middle", font_size=13,
        )
        att_header.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        box.add_widget(att_header)

        roll_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6))
        roll_row.add_widget(Label(text="Roll (deg) [Port up = +]", size_hint_x=0.65, font_size=12,
                                   halign="left", valign="middle"))
        self.roll_entry = TextInput(text="0.0", multiline=False, input_filter="float",
                                     size_hint_x=0.35, font_size=13)
        roll_row.add_widget(self.roll_entry)
        box.add_widget(roll_row)

        pitch_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6))
        pitch_row.add_widget(Label(text="Pitch (deg) [Bow up = +]", size_hint_x=0.65, font_size=12,
                                    halign="left", valign="middle"))
        self.pitch_entry = TextInput(text="0.0", multiline=False, input_filter="float",
                                      size_hint_x=0.35, font_size=13)
        pitch_row.add_widget(self.pitch_entry)
        box.add_widget(pitch_row)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8),
                             padding=(0, dp(8)))
        example_btn = Button(text="Load Example Values")
        example_btn.bind(on_release=self.load_example)
        btn_row.add_widget(example_btn)

        calc_btn = Button(text="Calculate Offsets ->", background_color=(0.2, 0.55, 0.3, 1))
        calc_btn.bind(on_release=self.calculate)
        btn_row.add_widget(calc_btn)
        box.add_widget(btn_row)

        self.add_widget(box)
        self.on_method_change(self.method_spinner, self.method_spinner.text)

    def on_method_change(self, spinner, text):
        method = "bucket" if text == "With bucket center" else "boompin_perp"
        row = self.point_rows["bucket"]
        if method == "bucket":
            row.set_enabled(True)
            self.bucket_hint.text = "Bucket Center is required for 'With bucket center'."
        else:
            row.clear()
            row.set_enabled(False)
            self.bucket_hint.text = "Bucket Center is not used for 'Without bucket center' (disabled)."

    def current_method(self):
        return "bucket" if self.method_spinner.text == "With bucket center" else "boompin_perp"

    def load_example(self, *args):
        self.method_spinner.text = "With bucket center"
        example = {
            "primary":   (10.250, 20.400, 5.120),
            "secondary": (9.800, 19.600, 5.080),
            "bp_port":   (10.000, 18.500, 4.200),
            "bp_stbd":   (9.550, 18.550, 4.210),
            "bucket":    (13.900, 21.800, 3.750),
        }
        for key, (x, y, z) in example.items():
            self.point_rows[key].set_point(x, y, z)
        self.roll_entry.text = "2.5"
        self.pitch_entry.text = "-1.8"

    def read_points(self):
        pts = {}
        for key, label in cl.POINT_LABELS:
            required = not (key == "bucket" and self.current_method() != "bucket")
            try:
                pts[key] = self.point_rows[key].get_point(required=required)
            except ValueError as e:
                raise ValueError(f"{label}: {e}")
        return pts

    def calculate(self, *args):
        try:
            pts = self.read_points()
        except ValueError as e:
            show_error("Input error", str(e))
            return
        try:
            roll_deg = float(self.roll_entry.text.strip() or "0")
            pitch_deg = float(self.pitch_entry.text.strip() or "0")
        except ValueError:
            show_error("Input error", "Roll and Pitch must be numeric (degrees).")
            return

        try:
            res = cl.compute_results(pts, roll_deg=roll_deg, pitch_deg=pitch_deg,
                                      heading_method=self.current_method())
        except ValueError as e:
            show_error("Input error", str(e))
            return

        self.app.last_results = res
        self.app.on_results_calculated(res)


# ----------------------------------------------------------------------
# Tab 3 - Computed Offsets & Diagrams
# ----------------------------------------------------------------------
class DiagramTab(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)

        diagrams = BoxLayout(orientation="vertical", size_hint_y=0.55, spacing=dp(4))
        self.plan_view = PlanViewDiagram(size_hint_y=0.55)
        self.angle_view = AngleConstructionDiagram(size_hint_y=0.45)
        diagrams.add_widget(self.plan_view)
        diagrams.add_widget(self.angle_view)
        self.add_widget(diagrams)

        results_header = Label(text="Formulas & Results", size_hint_y=None, height=dp(28),
                                bold=True, halign="left", valign="middle")
        results_header.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(results_header)

        self.results_panel = ResultsPanel(size_hint_y=0.45)
        self.results_panel.set_message("Enter survey data on tab 2 and click 'Calculate Offsets'.")
        self.add_widget(self.results_panel)

    def update_from_results(self, r):
        self.plan_view.set_data(r)
        self.angle_view.set_data(r)

        o = r["origin"]
        po = r["primary_off"]
        so = r["secondary_off"]
        pl = r["primary_local"]
        sl = r["secondary_local"]

        lines = []
        lines.append(("=== 1. MACHINE ORIGIN (Boom Pin Center) ===", False))
        lines.append(("Formula: Origin = (BoomPin_Port + BoomPin_Stbd) / 2", False))
        lines.append((f"BOOM PIN CENTER  X={o[0]:.3f}  Y={o[1]:.3f}  Z={o[2]:.3f}", True))

        lines.append(("=== 2. MACHINE ATTITUDE AT SURVEY TIME ===", False))
        lines.append((f"Roll (Port up=+) = {r['roll_deg']:+.3f} deg", False))
        lines.append((f"Pitch (Bow up=+) = {r['pitch_deg']:+.3f} deg", False))

        lines.append(("=== 3. SURVEY (WORLD) FRAME OFFSETS ===", False))
        lines.append((f"Primary   dX={po[0]:.3f} dY={po[1]:.3f} dZ={po[2]:.3f}", False))
        lines.append((f"Secondary dX={so[0]:.3f} dY={so[1]:.3f} dZ={so[2]:.3f}", False))

        lines.append(("=== 4. BODY FRAME OFFSETS (tilt-corrected) - TO BE USED ===", False))
        lines.append(("Axes: Fwd(Y)=Forward, Right(X)=Right/Stbd, Up(Z)=Up", False))
        lines.append((f"Primary   Fwd(Y)={pl[0]:.3f} Right(X)={pl[1]:.3f} Up(Z)={pl[2]:.3f}", True))
        lines.append((f"Secondary Fwd(Y)={sl[0]:.3f} Right(X)={sl[1]:.3f} Up(Z)={sl[2]:.3f}", True))

        lines.append(("=== 5. HEADING OFFSET ===", False))
        if r["heading_method"] == "bucket":
            lines.append(("Method: WITH BUCKET CENTER", False))
            lines.append(("Ref line thru Origin, perp. to Origin->Bucket direction.", False))
        else:
            lines.append(("Method: WITHOUT BUCKET CENTER (legacy-sheet method)", False))
            lines.append(("Ref line = BoomPin_Port -> BoomPin_Stbd baseline.", False))
        lines.append(("Perpendicular dropped from Primary onto ref line -> C1.", False))
        lines.append(("HeadingOffset = LawOfCosines angle at Primary between", False))
        lines.append(("(Primary->Secondary) and (Primary->C1).", False))
        lines.append((f"Da (baseline)         = {r['loc_Da']:.4f}", False))
        lines.append((f"Db (Primary->C1)      = {r['loc_Db']:.4f}", False))
        lines.append((f"Dc (Secondary->C1)    = {r['loc_Dc']:.4f}", False))
        lines.append((f"acos(cos_angle) = acos({r['loc_cos_ang']:.6f})", False))
        lines.append((f"HEADING OFFSET = {r['heading_offset']:+.3f} deg", True))
        lines.append(("(add this to raw GNSS heading to get true machine heading)", False))

        lines.append(("=== 6. REFERENCE DISTANCES ===", False))
        lines.append((f"Antenna baseline length = {r['baseline_dist']:.3f}", False))
        if r["have_bucket"]:
            lines.append((f"Origin -> Bucket distance = {r['boom_to_bucket_dist']:.3f}", False))
        else:
            lines.append(("Origin -> Bucket distance = (not measured)", False))

        self.results_panel.set_lines(lines)


# ----------------------------------------------------------------------
# Tab 4 - Cross-Verify Grid Heading
# ----------------------------------------------------------------------
class VerifyTab(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.app = app

        top_scroll = ScrollView(size_hint_y=0.5)
        box = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(10), spacing=dp(6))
        box.bind(minimum_height=box.setter("height"))

        instr = Label(
            text="Independent field check: shoot two points with an RTK GPS rover in your "
                 "chosen UTM system - Bucket Center, and a point on the machine's aft/"
                 "centerline axis. Compare the resulting grid heading against the raw GNSS "
                 "heading corrected by the tab-3 heading offset.",
            size_hint_y=None, halign="left", valign="top", font_size=12,
        )
        instr.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        instr.bind(texture_size=lambda inst, ts: setattr(inst, "height", ts[1] + dp(10)))
        box.add_widget(instr)

        utm_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(6))
        utm_row.add_widget(Label(text="Datum: WGS84   UTM Zone:", size_hint_x=0.5, font_size=12))
        self.zone_spinner = Spinner(text="43", values=[str(z) for z in range(1, 61)],
                                     size_hint_x=0.25, font_size=12)
        utm_row.add_widget(self.zone_spinner)
        self.hemi_spinner = Spinner(text="N", values=["N", "S"], size_hint_x=0.25, font_size=12)
        utm_row.add_widget(self.hemi_spinner)
        box.add_widget(utm_row)

        col_header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(22))
        col_header.add_widget(Label(text="Point", size_hint_x=0.45, bold=True, font_size=11))
        col_header.add_widget(Label(text="X (East)", size_hint_x=0.275, bold=True, font_size=11))
        col_header.add_widget(Label(text="Y (North)", size_hint_x=0.275, bold=True, font_size=11))
        box.add_widget(col_header)

        self.bucket_row = PointEntryRow2D("Bucket Center (GPS)")
        self.aft_row = PointEntryRow2D("Aft/Centerline Pt (GPS)")
        box.add_widget(self.bucket_row)
        box.add_widget(self.aft_row)

        raw_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(60), spacing=dp(6))
        raw_lbl = Label(text="Raw antenna-baseline heading on machine's GNSS display "
                              "(deg, 0-360):", size_hint_x=0.7, font_size=12, halign="left",
                         valign="middle")
        raw_lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        raw_row.add_widget(raw_lbl)
        self.raw_heading_entry = TextInput(multiline=False, input_filter="float", size_hint_x=0.3,
                                            font_size=13)
        raw_row.add_widget(self.raw_heading_entry)
        box.add_widget(raw_row)

        verify_btn = Button(text="Verify Grid Heading ->", size_hint_y=None, height=dp(46),
                             background_color=(0.2, 0.55, 0.3, 1))
        verify_btn.bind(on_release=self.verify)
        box.add_widget(verify_btn)

        top_scroll.add_widget(box)
        self.add_widget(top_scroll)

        self.diagram = GridHeadingDiagram(size_hint_y=0.25)
        self.add_widget(self.diagram)

        self.results_panel = ResultsPanel(size_hint_y=0.25)
        self.results_panel.set_message(
            "Calculate the heading offset on tab 3 first, then enter the two GPS-rover "
            "shots and the machine's live raw heading here."
        )
        self.add_widget(self.results_panel)

    def verify(self, *args):
        if self.app.last_results is None:
            show_error("Heading offset not calculated",
                        "Calculate the heading offset on tab 3 first.")
            return
        try:
            gps_bucket = self.bucket_row.get_point()
            gps_aft = self.aft_row.get_point()
        except ValueError as e:
            show_error("Input error", str(e))
            return
        try:
            raw_heading_deg = float(self.raw_heading_entry.text.strip())
        except ValueError:
            show_error("Input error", "Raw antenna-baseline heading must be numeric (degrees).")
            return

        heading_offset_deg = self.app.last_results["heading_offset"]
        v = cl.compute_grid_heading_check(gps_bucket, gps_aft, raw_heading_deg, heading_offset_deg)

        self.diagram.set_data(v)

        zone_label = f"WGS84 UTM Zone {self.zone_spinner.text}{self.hemi_spinner.text}"
        lines = []
        lines.append((f"Coordinate system: {zone_label}", False))
        lines.append(("=== GRID HEADING (measured by GPS rover) ===", False))
        lines.append(("Formula: atan2(dEasting, dNorthing) of (Bucket - AftPoint)", False))
        lines.append((f"Baseline length = {v['baseline_length']:.3f}", False))
        lines.append((f"GRID HEADING = {v['grid_heading']:.3f} deg", True))
        lines.append(("=== CORRECTED (CALIBRATED) HEADING ===", False))
        lines.append(("Formula: (RawAntennaHeading + HeadingOffset) mod 360", False))
        lines.append((f"Raw heading = {v['raw_heading_deg']:.3f} deg", False))
        lines.append((f"Heading offset (tab 3) = {v['heading_offset_deg']:+.3f} deg", False))
        lines.append((f"CORRECTED HEADING = {v['corrected_heading']:.3f} deg", True))
        lines.append(("=== RESIDUAL ===", False))
        lines.append((f"RESIDUAL = {v['residual']:+.3f} deg", False))
        lines.append(("(should be close to 0 if calibration is good)", False))
        self.results_panel.set_lines(lines)


# ----------------------------------------------------------------------
# App
# ----------------------------------------------------------------------
class ExcavatorOffsetApp(App):
    def build(self):
        self.title = "Excavator Offset Calculator"
        self.last_results = None

        root = BoxLayout(orientation="vertical")

        topbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36),
                            padding=(dp(8), 0))
        title_lbl = Label(text="Excavator Offset Calculator", bold=True, halign="left",
                           valign="middle", font_size=15)
        title_lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        topbar.add_widget(title_lbl)
        credit_lbl = Label(text="By: Bharath Bommeeshwar Kumar", italic=True, halign="right",
                            valign="middle", font_size=11, color=(0.6, 0.6, 0.6, 1))
        credit_lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        topbar.add_widget(credit_lbl)
        root.add_widget(topbar)

        tabs = TabbedPanel(do_default_tab=False, tab_pos="top_mid")

        t1 = TabbedPanelItem(text="1.Ref")
        t1.font_size = "12sp"
        t1.add_widget(build_reference_tab())
        tabs.add_widget(t1)

        t2 = TabbedPanelItem(text="2.Input")
        t2.font_size = "12sp"
        self.input_tab = InputTab(self)
        t2.add_widget(self.input_tab)
        tabs.add_widget(t2)

        t3 = TabbedPanelItem(text="3.Results")
        t3.font_size = "12sp"
        self.diagram_tab = DiagramTab()
        t3.add_widget(self.diagram_tab)
        tabs.add_widget(t3)

        t4 = TabbedPanelItem(text="4.Verify")
        t4.font_size = "12sp"
        self.verify_tab = VerifyTab(self)
        t4.add_widget(self.verify_tab)
        tabs.add_widget(t4)

        root.add_widget(tabs)
        return root

    def on_results_calculated(self, res):
        self.diagram_tab.update_from_results(res)


if __name__ == "__main__":
    ExcavatorOffsetApp().run()
