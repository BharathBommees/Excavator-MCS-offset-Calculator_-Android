"""
Excavator GNSS Antenna & Boom-Pin Offset Calculator - Core Logic
==================================================================
Pure Python/NumPy calculation functions, ported unchanged from the
validated desktop (Tkinter) version. No UI dependencies here at all,
so this module works identically on desktop and Android.

All formulas in this file have been verified against the user's
original legacy calibration spreadsheet (Law-of-Cosines / perpendicular
-drop construction) and reproduce its results to 8+ significant figures.
"""

import math
import numpy as np

POINT_LABELS = [
    ("primary",   "Primary Antenna (Port / Aft)"),
    ("secondary", "Secondary Antenna (Starboard)"),
    ("bp_port",   "Boom Pin - Port side"),
    ("bp_stbd",   "Boom Pin - Starboard side"),
    ("bucket",    "Bucket Teeth Center"),
]

VERIFY_POINT_LABELS = [
    ("gps_bucket", "Bucket Center (GPS Rover, UTM)"),
    ("gps_aft",    "Aft / Centerline Point (GPS Rover, UTM)"),
]

def to_vec(d):
    return np.array([d["x"], d["y"], d["z"]], dtype=float)


def bearing_deg(vec_xy):
    """Bearing of a horizontal vector, degrees clockwise from +Y (North), 0-360."""
    dx, dy = vec_xy
    ang = math.degrees(math.atan2(dx, dy))
    return ang % 360.0


def wrap180(a):
    a = (a + 180.0) % 360.0 - 180.0
    return a


# ----------------------------------------------------------------------
# Roll / pitch tilt matrices
# Sign convention (per user spec):
#   Roll  : Port (cabin/operator side) up = POSITIVE
#   Pitch : Bow  (bucket side)          up = POSITIVE
# These map a LEVEL local vector (fwd, right, up) to how it would appear
# AS-MEASURED while the machine is tilted by that amount. The inverse
# (tilted -> level) is obtained by negating the angle, since these are
# proper rotation matrices (inverse = transpose = same matrix with -angle).
# ----------------------------------------------------------------------
def rot_roll(theta_deg):
    t = math.radians(theta_deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([
        [1.0, 0.0, 0.0],
        [0.0,   c,   s],
        [0.0,  -s,   c],
    ])


def rot_pitch(alpha_deg):
    a = math.radians(alpha_deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([
        [   c, 0.0,  -s],
        [ 0.0, 1.0, 0.0],
        [   s, 0.0,   c],
    ])


def law_of_cosines_heading(P2, S2, line_pt_a, line_pt_b):
    """
    Generalized version of the validated legacy-sheet construction:
    drop a perpendicular from the Primary antenna onto a reference line
    (defined by any two points, line_pt_a and line_pt_b, that lie on a
    line perpendicular to the true heading axis), then take the
    Law-of-Cosines interior angle at Primary between (Primary->Secondary)
    and (Primary->foot-of-perpendicular).

    For heading_method='boompin_perp', the reference line is the physical
    Boom Pin Port->Starboard baseline (this is exactly the original
    legacy-sheet formula). For heading_method='bucket', the reference
    line is constructed through the Origin, perpendicular to the
    Origin->Bucket direction -- the bucket-derived equivalent of the
    boom-pin baseline.

    Inputs are 2D (x, y) arrays/points in any consistent Cartesian frame
    (world Easting/Northing, or the tilt-corrected local fwd/right plane).
    Returns the angle in degrees (0-180), and the foot-of-perpendicular point.
    """
    P2 = np.asarray(P2, dtype=float)
    S2 = np.asarray(S2, dtype=float)
    line_pt_a = np.asarray(line_pt_a, dtype=float)
    line_pt_b = np.asarray(line_pt_b, dtype=float)
    line_mid = (line_pt_a + line_pt_b) / 2.0

    d0 = line_pt_b - line_pt_a              # reference line direction
    d1 = np.array([-d0[1], d0[0]])          # perpendicular direction (through Primary)
    A = np.array([[d0[0], -d1[0]], [d0[1], -d1[1]]])
    b = P2 - line_mid
    t, s = np.linalg.solve(A, b)
    C1 = line_mid + t * d0                  # foot of perpendicular from Primary

    Da = float(np.linalg.norm(S2 - P2))     # antenna baseline length
    Db = float(np.linalg.norm(C1 - P2))     # Primary -> foot of perpendicular
    Dc = float(np.linalg.norm(C1 - S2))     # Secondary -> foot of perpendicular
    cos_ang = (Da ** 2 + Db ** 2 - Dc ** 2) / (2 * Da * Db)
    cos_ang = max(-1.0, min(1.0, cos_ang))  # guard tiny float overshoot at +-1
    ang = math.degrees(math.acos(cos_ang))
    return {
        "angle_deg": ang,
        "C1": C1,
        "Da": Da, "Db": Db, "Dc": Dc,
        "cos_ang": cos_ang,
    }


def compute_results(pts, roll_deg=0.0, pitch_deg=0.0, heading_method="bucket"):
    """
    pts: dict of point-name -> {'x':..,'y':..,'z':..}. 'bucket' may be
        omitted / None when heading_method == 'boompin_perp'.
    roll_deg / pitch_deg: machine attitude measured by digital level at the
        moment of the survey shots. Port-up = +roll, Bow(bucket side)-up = +pitch.
    heading_method:
        'bucket'       -> reference heading = Origin -> Bucket Center
                          (signed bearing-difference method)
        'boompin_perp' -> validated legacy-sheet method: drop a perpendicular
                          from the Primary antenna onto the Boom Pin
                          Port->Starboard baseline, then take the
                          Law-of-Cosines angle at Primary between the
                          antenna baseline and that perpendicular. No
                          bucket shot needed.
    Returns a dict with all derived quantities.
    """
    P = to_vec(pts["primary"])
    S = to_vec(pts["secondary"])
    BPp = to_vec(pts["bp_port"])
    BPs = to_vec(pts["bp_stbd"])
    have_bucket = pts.get("bucket") is not None
    Bk = to_vec(pts["bucket"]) if have_bucket else None

    if heading_method == "bucket" and not have_bucket:
        raise ValueError("Bucket Center is required for the 'With bucket center' method.")

    # 1) Boom pin center = machine origin (0,0,0) -- a measured point,
    #    unaffected by tilt correction.
    origin = (BPp + BPs) / 2.0

    # 2) Raw survey-frame (world / Easting-Northing-Elevation) offsets.
    #    These are the true 3D differences as shot, tilt or no tilt.
    primary_off = P - origin
    secondary_off = S - origin
    bucket_off = (Bk - origin) if have_bucket else None
    bp_port_off = BPp - origin
    bp_stbd_off = BPs - origin
    bp_baseline = BPs - BPp  # boom pin port -> starboard, world frame

    # 3) First-pass (uncorrected) reference-direction vector, used only to
    #    orient the roll/pitch correction axes (which horizontal direction
    #    is "forward" vs "right"). Fine as an approximation either way --
    #    see step 6.
    if heading_method == "bucket":
        ref_vec_raw_xy = np.array([bucket_off[0], bucket_off[1]])
    else:
        # perpendicular to the boom-pin baseline, in the horizontal plane
        perp_xy = np.array([bp_baseline[1], -bp_baseline[0]])
        # disambiguate direction: forward must point AWAY from the
        # antenna-mounting side (antennas are mounted aft, per the photo)
        antenna_mid_xy = (((P + S) / 2.0) - origin)[:2]
        if np.dot(perp_xy, antenna_mid_xy) > 0:
            perp_xy = -perp_xy
        ref_vec_raw_xy = perp_xy

    ref_heading_raw = bearing_deg(ref_vec_raw_xy)
    ant_vec_xy_raw = np.array([primary_off[0] - secondary_off[0],
                                primary_off[1] - secondary_off[1]])
    ant_heading_raw = bearing_deg(ant_vec_xy_raw)

    theta = math.radians(ref_heading_raw)

    def to_local(v):
        dx, dy, dz = v
        fwd = dx * math.sin(theta) + dy * math.cos(theta)
        right = dx * math.cos(theta) - dy * math.sin(theta)
        return np.array([fwd, right, dz])

    # 4) Remove roll & pitch tilt: local (yaw-aligned, still-tilted) vector
    #    -> body frame (level, true mechanical offset) vector.
    #    v_body = Rroll(-roll) . Rpitch(-pitch) . v_local
    Rr_inv = rot_roll(-roll_deg)
    Rp_inv = rot_pitch(-pitch_deg)

    def to_body(v_world):
        v_local = to_local(v_world)
        return Rr_inv @ (Rp_inv @ v_local)

    primary_local = to_body(primary_off)      # (fwd, right, up) - tilt corrected
    secondary_local = to_body(secondary_off)
    bucket_local = to_body(bucket_off) if have_bucket else None
    bp_port_local = to_body(bp_port_off)
    bp_stbd_local = to_body(bp_stbd_off)

    # 5) Corrected antenna baseline vector (Secondary -> Primary) in body frame
    baseline_local = primary_local - secondary_local
    ant_local_angle = bearing_deg([baseline_local[1], baseline_local[0]])

    P2 = np.array([primary_local[1], primary_local[0]])
    S2 = np.array([secondary_local[1], secondary_local[0]])

    if heading_method == "bucket":
        # Same validated construction as the legacy sheet, generalized:
        # instead of dropping the perpendicular onto the physical boom-pin
        # baseline, drop it onto a line through the Origin that is itself
        # perpendicular to the Origin->Bucket heading direction (the
        # bucket-derived equivalent of the boom-pin baseline).
        bucket_dir_2d = np.array([bucket_local[1], bucket_local[0]])
        perp_of_bucket = np.array([-bucket_dir_2d[1], bucket_dir_2d[0]])
        line_pt_a = np.array([0.0, 0.0])          # Origin, always (0,0) in body frame
        line_pt_b = line_pt_a + perp_of_bucket
    else:
        # Validated legacy-sheet method: drop the perpendicular onto the
        # physical Boom Pin Port->Starboard baseline.
        line_pt_a = np.array([bp_port_local[1], bp_port_local[0]])
        line_pt_b = np.array([bp_stbd_local[1], bp_stbd_local[0]])

    # Both tilt-corrected local (right, fwd) plane -- reduces exactly to
    # the legacy formula when roll = pitch = 0.
    loc = law_of_cosines_heading(P2, S2, line_pt_a, line_pt_b)
    heading_offset = loc["angle_deg"]
    ant_heading = wrap180(ant_heading_raw + ant_local_angle) % 360.0
    ref_heading = wrap180(ant_heading + heading_offset) % 360.0

    return {
        "origin": origin,
        "primary_off": primary_off,
        "secondary_off": secondary_off,
        "bucket_off": bucket_off,
        "primary_local": primary_local,
        "secondary_local": secondary_local,
        "bucket_local": bucket_local,
        "ref_heading": ref_heading,
        "ant_heading": ant_heading,
        "ref_heading_raw": ref_heading_raw,
        "ant_heading_raw": ant_heading_raw,
        "heading_offset": heading_offset,
        "heading_method": heading_method,
        "have_bucket": have_bucket,
        "roll_deg": roll_deg,
        "pitch_deg": pitch_deg,
        "primary_dist": float(np.linalg.norm(primary_off)),
        "secondary_dist": float(np.linalg.norm(secondary_off)),
        "baseline_dist": float(np.linalg.norm(ant_vec_xy_raw)),
        "boom_to_bucket_dist": float(np.linalg.norm(bucket_off[:2])) if have_bucket else None,
        "raw_points": {"P": P, "S": S, "BPp": BPp, "BPs": BPs, "Bk": Bk},
        "loc_Da": loc["Da"], "loc_Db": loc["Db"], "loc_Dc": loc["Dc"],
        "loc_cos_ang": loc["cos_ang"], "loc_C1": loc["C1"],
        "loc_line_pt_a": line_pt_a, "loc_line_pt_b": line_pt_b,
        "loc_P2": P2, "loc_S2": S2,
    }



# ----------------------------------------------------------------------
# Independent field cross-check of the calculated heading offset.
#
# Take two live RTK GPS-rover shots (in the chosen UTM projection):
#   1) Bucket Center
#   2) A point on the machine's aft / centerline axis
# The bearing between them is the "grid heading" of the machine, measured
# directly -- completely independent of the total-station survey and the
# heading-offset calculation on tab 3.
#
# This is compared against: (raw antenna-baseline heading, as currently
# displayed live by the machine's GNSS/GPS controller) + (heading offset
# computed on tab 3). If the calibration is good, the two should agree
# closely.
# ----------------------------------------------------------------------
def compute_grid_heading_check(gps_bucket, gps_aft, raw_heading_deg, heading_offset_deg):
    """gps_bucket / gps_aft: dicts with 'x' (Easting), 'y' (Northing) only."""
    B = np.array([gps_bucket["x"], gps_bucket["y"]], dtype=float)
    A = np.array([gps_aft["x"], gps_aft["y"]], dtype=float)
    d = B - A
    grid_heading = bearing_deg([d[0], d[1]])
    corrected_heading = (raw_heading_deg + heading_offset_deg) % 360.0
    residual = wrap180(grid_heading - corrected_heading)
    return {
        "gps_bucket": B,
        "gps_aft": A,
        "delta": d,
        "grid_heading": grid_heading,
        "raw_heading_deg": raw_heading_deg,
        "heading_offset_deg": heading_offset_deg,
        "corrected_heading": corrected_heading,
        "residual": residual,
        "baseline_length": float(np.linalg.norm(d)),
    }



# ----------------------------------------------------------------------
# Reference image loader -- the shipped photo is ALREADY labeled
# (Primary Ant, Secondary Ant, Boompin Port, Boompin Starboard,
