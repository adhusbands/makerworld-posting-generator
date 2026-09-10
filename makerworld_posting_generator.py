#!/usr/bin/env python3
"""
MakerWorld Posting Generator
-----------------------------
A simple desktop app (Tkinter, stdlib-only) that reads an STL or 3MF file,
analyzes the geometry, and drafts a ready-to-paste MakerWorld posting:
title, description, tags, and a suggested category.

IMPORTANT: MakerWorld has no public API for creating drafts or uploads, so
this tool cannot push anything to your MakerWorld account automatically.
It generates the text/content for you to paste into MakerWorld's own
upload form (makerworld.com -> Upload).

No third-party packages required — just Python 3's standard library,
including tkinter (which ships with the standard python.org Windows
installer).

Run with:
    python makerworld_posting_generator.py
"""

import os
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ---------------------------------------------------------------------------
# Material densities in g/cm^3, used for rough weight estimates
# ---------------------------------------------------------------------------
MATERIAL_DENSITIES = {
    "PLA": 1.24,
    "PETG": 1.27,
    "ABS": 1.04,
    "ASA": 1.05,
    "TPU": 1.21,
    "Nylon": 1.14,
    "PC": 1.20,
}

CATEGORY_HINTS = [
    ("gear", "Mechanical & Engineering"),
    ("bracket", "Mechanical & Engineering"),
    ("mount", "Mechanical & Engineering"),
    ("holder", "Organization"),
    ("stand", "Home Decor"),
    ("case", "Gadget & Electronics"),
    ("box", "Organization"),
    ("vase", "Home Decor"),
    ("toy", "Toys & Games"),
    ("figure", "Toys & Games"),
    ("miniature", "Toys & Games"),
    ("mini", "Toys & Games"),
    ("jewelry", "Fashion & Accessories"),
    ("ring", "Fashion & Accessories"),
    ("keychain", "Fashion & Accessories"),
    ("tool", "Tools & Gadgets"),
    ("garden", "Garden & Outdoors"),
    ("cosplay", "Cosplay & Props"),
    ("prop", "Cosplay & Props"),
]


# ---------------------------------------------------------------------------
# STL parsing (binary + ASCII)
# ---------------------------------------------------------------------------
def parse_stl(path):
    """Return a list of triangles, each a tuple of 3 (x, y, z) vertices."""
    with open(path, "rb") as f:
        header = f.read(80)
        rest = f.read()

    # Heuristic: ASCII STL files start with "solid" and contain "facet normal"
    is_ascii = header.strip().lower().startswith(b"solid") and b"facet" in (header + rest[:2000]).lower()

    if is_ascii:
        return _parse_stl_ascii(header + rest)
    else:
        return _parse_stl_binary(rest)


def _parse_stl_binary(data):
    triangle_count = struct.unpack("<I", data[:4])[0]
    triangles = []
    offset = 4
    for _ in range(triangle_count):
        # normal (3 floats) + 3 vertices (3 floats each) + 2-byte attribute
        chunk = data[offset:offset + 50]
        if len(chunk) < 50:
            break
        vals = struct.unpack("<12fH", chunk)
        v0 = vals[3:6]
        v1 = vals[6:9]
        v2 = vals[9:12]
        triangles.append((v0, v1, v2))
        offset += 50
    return triangles


def _parse_stl_ascii(data):
    text = data.decode("utf-8", errors="ignore")
    coords = re.findall(
        r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", text
    )
    floats = [(float(a), float(b), float(c)) for a, b, c in coords]
    triangles = []
    for i in range(0, len(floats) - 2, 3):
        triangles.append((floats[i], floats[i + 1], floats[i + 2]))
    return triangles


# ---------------------------------------------------------------------------
# 3MF parsing (zip archive containing 3D/3dmodel.model XML)
# ---------------------------------------------------------------------------
def parse_3mf(path):
    """Return (triangles, metadata_dict, object_count)."""
    triangles = []
    metadata = {}
    object_count = 0

    with zipfile.ZipFile(path, "r") as z:
        model_path = None
        for name in z.namelist():
            if name.lower().endswith("3dmodel.model"):
                model_path = name
                break
        if model_path is None:
            raise ValueError("No 3dmodel.model found inside the 3MF file.")

        xml_data = z.read(model_path)
        root = ET.fromstring(xml_data)

        # Namespace-agnostic helper
        def local(tag):
            return tag.split("}")[-1]

        # Metadata (title, designer, description, application, etc.)
        for elem in root.iter():
            if local(elem.tag) == "metadata":
                key = elem.attrib.get("name", "")
                if key and elem.text:
                    metadata[key] = elem.text.strip()

        # Objects -> mesh -> vertices/triangles
        objects = [e for e in root.iter() if local(e.tag) == "object"]
        object_count = len(objects)

        for obj in objects:
            mesh = None
            for child in obj.iter():
                if local(child.tag) == "mesh":
                    mesh = child
                    break
            if mesh is None:
                continue

            verts = []
            for v in mesh.iter():
                if local(v.tag) == "vertex":
                    verts.append((
                        float(v.attrib["x"]),
                        float(v.attrib["y"]),
                        float(v.attrib["z"]),
                    ))

            for t in mesh.iter():
                if local(t.tag) == "triangle":
                    i1 = int(t.attrib["v1"])
                    i2 = int(t.attrib["v2"])
                    i3 = int(t.attrib["v3"])
                    if i1 < len(verts) and i2 < len(verts) and i3 < len(verts):
                        triangles.append((verts[i1], verts[i2], verts[i3]))

    return triangles, metadata, object_count


# ---------------------------------------------------------------------------
# Geometry analysis
# ---------------------------------------------------------------------------
def analyze_mesh(triangles):
    if not triangles:
        raise ValueError("No triangles could be read from this file.")

    xs, ys, zs = [], [], []
    volume_sum = 0.0
    area_sum = 0.0

    for v0, v1, v2 in triangles:
        for v in (v0, v1, v2):
            xs.append(v[0])
            ys.append(v[1])
            zs.append(v[2])

        # Signed volume of tetrahedron formed with origin (divergence theorem)
        volume_sum += (
            v0[0] * (v1[1] * v2[2] - v1[2] * v2[1])
            - v0[1] * (v1[0] * v2[2] - v1[2] * v2[0])
            + v0[2] * (v1[0] * v2[1] - v1[1] * v2[0])
        ) / 6.0

        # Triangle surface area via cross product
        ux, uy, uz = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
        wx, wy, wz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
        cx = uy * wz - uz * wy
        cy = uz * wx - ux * wz
        cz = ux * wy - uy * wx
        area_sum += 0.5 * (cx ** 2 + cy ** 2 + cz ** 2) ** 0.5

    volume_mm3 = abs(volume_sum)
    dims = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    return {
        "dims_mm": dims,
        "volume_mm3": volume_mm3,
        "volume_cm3": volume_mm3 / 1000.0,
        "surface_area_mm2": area_sum,
        "triangle_count": len(triangles),
    }


def estimate_weight_g(volume_cm3, material, infill_percent, shell_ratio=0.25):
    """Very rough weight estimate. Assumes `shell_ratio` of the volume is
    solid shells/walls and the remainder is filled at `infill_percent`."""
    density = MATERIAL_DENSITIES.get(material, 1.24)
    effective_fraction = shell_ratio + (1 - shell_ratio) * (infill_percent / 100.0)
    return volume_cm3 * density * effective_fraction


def guess_category(name_tokens):
    for token in name_tokens:
        for hint, category in CATEGORY_HINTS:
            if hint in token:
                return category
    return "Home Decor"  # sensible generic fallback


def guess_tags(name_tokens, dims_mm, object_count):
    tags = set()
    for token in name_tokens:
        if len(token) > 2:
            tags.add(token.lower())

    tags.add("3d printing")
    tags.add("3d print")

    largest_dim = max(dims_mm)
    if largest_dim <= 60:
        tags.add("small print")
    elif largest_dim >= 200:
        tags.add("large print")

    if object_count and object_count > 1:
        tags.add("multi-part")

    return sorted(tags)[:13]  # MakerWorld caps tags; keep a reasonable number


# ---------------------------------------------------------------------------
# Posting text generation
# ---------------------------------------------------------------------------
def generate_posting(display_name, analysis, material, infill, object_count, mf_metadata=None):
    dims = analysis["dims_mm"]
    volume_cm3 = analysis["volume_cm3"]
    weight = estimate_weight_g(volume_cm3, material, infill)

    name_tokens = re.split(r"[\s_\-]+", display_name.lower())
    category = guess_category(name_tokens)
    tags = guess_tags(name_tokens, dims, object_count)

    title = display_name.strip()
    if not title:
        title = "Untitled Model"
    # Title-case it nicely if it looks like a raw filename
    if title == title.lower() or title == title.upper():
        title = title.title()

    designer_note = ""
    if mf_metadata:
        d = mf_metadata.get("Designer") or mf_metadata.get("Author")
        if d:
            designer_note = f"\n_Originally modeled by {d}._\n"

    description = f"""## {title}

{designer_note}
**What it is**
A {"multi-part " if object_count and object_count > 1 else ""}3D printable design ({dims[0]:.0f} x {dims[1]:.0f} x {dims[2]:.0f} mm). Describe here what it's for and why someone would want to print it — replace this line with 1-3 sentences about the model's purpose.

**Model Stats**
- Dimensions: {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm (L x W x H, as oriented in the source file)
- Estimated volume: {volume_cm3:.1f} cm^3
- Estimated weight: ~{weight:.0f} g in {material} at {infill}% infill (varies with your actual slicer settings)
- Parts in file: {object_count if object_count else 1}
- Triangle count: {analysis['triangle_count']:,}

**Recommended Print Settings**
- Material: {material}
- Layer height: 0.2 mm
- Infill: {infill}%
- Supports: check your slicer preview — add if overhangs exceed ~45 degrees
- Orientation: as provided in the file; reorient in your slicer if needed for better overhangs or strength

**Notes**
- No supports/hardware assumed beyond the printed parts above — edit this section if your design needs screws, magnets, bearings, etc.
- Replace this templated text with your own details before publishing; this draft is a starting point generated from the file's geometry, not a finished listing.
"""

    return {
        "title": title,
        "description": description.strip(),
        "tags": tags,
        "category": category,
    }


# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MakerWorld Posting Generator")
        self.geometry("760x760")
        self.minsize(680, 620)

        self.filepath = None
        self.analysis = None
        self.object_count = 1
        self.mf_metadata = {}

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # --- File picker row ---
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Button(top, text="Choose STL / 3MF file...", command=self.choose_file).pack(side="left")
        self.file_label = ttk.Label(top, text="No file selected", foreground="#555")
        self.file_label.pack(side="left", padx=10)

        # --- Options row ---
        opts = ttk.LabelFrame(self, text="Print settings for the estimate")
        opts.pack(fill="x", **pad)

        ttk.Label(opts, text="Material:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.material_var = tk.StringVar(value="PLA")
        material_combo = ttk.Combobox(
            opts, textvariable=self.material_var, values=list(MATERIAL_DENSITIES.keys()),
            state="readonly", width=10
        )
        material_combo.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        ttk.Label(opts, text="Infill %:").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self.infill_var = tk.IntVar(value=15)
        infill_spin = ttk.Spinbox(opts, from_=0, to=100, textvariable=self.infill_var, width=6)
        infill_spin.grid(row=0, column=3, padx=8, pady=8, sticky="w")

        ttk.Label(opts, text="Model name / title:").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        self.name_var = tk.StringVar(value="")
        name_entry = ttk.Entry(opts, textvariable=self.name_var, width=40)
        name_entry.grid(row=1, column=1, columnspan=3, padx=8, pady=8, sticky="we")

        ttk.Button(self, text="Analyze File + Generate Posting", command=self.run_generation).pack(**pad)

        # --- Stats summary ---
        self.stats_label = ttk.Label(self, text="", justify="left", foreground="#333")
        self.stats_label.pack(fill="x", **pad)

        # --- Output notebook ---
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, **pad)

        # Title tab
        title_frame = ttk.Frame(notebook)
        notebook.add(title_frame, text="Title")
        self.title_entry = ttk.Entry(title_frame, font=("Segoe UI", 11))
        self.title_entry.pack(fill="x", padx=10, pady=10)
        ttk.Button(title_frame, text="Copy Title", command=lambda: self.copy_text(self.title_entry.get())).pack(pady=4)

        # Description tab
        desc_frame = ttk.Frame(notebook)
        notebook.add(desc_frame, text="Description")
        self.desc_text = scrolledtext.ScrolledText(desc_frame, wrap="word", font=("Consolas", 10))
        self.desc_text.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Button(desc_frame, text="Copy Description", command=lambda: self.copy_text(self.desc_text.get("1.0", "end"))).pack(pady=4)

        # Tags/Category tab
        tags_frame = ttk.Frame(notebook)
        notebook.add(tags_frame, text="Tags & Category")
        ttk.Label(tags_frame, text="Suggested category:").pack(anchor="w", padx=10, pady=(10, 0))
        self.category_entry = ttk.Entry(tags_frame, font=("Segoe UI", 10))
        self.category_entry.pack(fill="x", padx=10, pady=4)

        ttk.Label(tags_frame, text="Suggested tags (comma separated):").pack(anchor="w", padx=10, pady=(10, 0))
        self.tags_entry = tk.Text(tags_frame, height=4, font=("Segoe UI", 10), wrap="word")
        self.tags_entry.pack(fill="x", padx=10, pady=4)
        ttk.Button(tags_frame, text="Copy Tags", command=lambda: self.copy_text(self.tags_entry.get("1.0", "end"))).pack(pady=4)

        # Bottom actions
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="Save Everything to .txt", command=self.save_all).pack(side="left")
        ttk.Button(bottom, text="Open MakerWorld Upload Page", command=self.open_makerworld).pack(side="left", padx=10)

        note = ttk.Label(
            self,
            text=("Note: MakerWorld has no public API for creating drafts, so this tool cannot post "
                  "for you automatically. Copy the generated text into MakerWorld's own Upload form."),
            foreground="#a05a00", wraplength=720, justify="left"
        )
        note.pack(fill="x", padx=10, pady=(0, 10))

    # -- Actions --
    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Select an STL or 3MF file",
            filetypes=[("3D model files", "*.stl *.3mf"), ("All files", "*.*")],
        )
        if not path:
            return
        self.filepath = path
        self.file_label.config(text=os.path.basename(path))
        base = os.path.splitext(os.path.basename(path))[0]
        pretty = re.sub(r"[_\-]+", " ", base).strip()
        self.name_var.set(pretty)

    def run_generation(self):
        if not self.filepath:
            messagebox.showwarning("No file", "Choose an STL or 3MF file first.")
            return

        try:
            ext = os.path.splitext(self.filepath)[1].lower()
            self.mf_metadata = {}
            self.object_count = 1

            if ext == ".stl":
                triangles = parse_stl(self.filepath)
            elif ext == ".3mf":
                triangles, self.mf_metadata, self.object_count = parse_3mf(self.filepath)
            else:
                messagebox.showerror("Unsupported file", "Please choose a .stl or .3mf file.")
                return

            self.analysis = analyze_mesh(triangles)
        except Exception as e:
            messagebox.showerror("Couldn't read file", f"Something went wrong reading this file:\n\n{e}")
            return

        material = self.material_var.get()
        infill = self.infill_var.get()
        display_name = self.name_var.get() or os.path.splitext(os.path.basename(self.filepath))[0]

        posting = generate_posting(
            display_name, self.analysis, material, infill, self.object_count, self.mf_metadata
        )

        dims = self.analysis["dims_mm"]
        self.stats_label.config(
            text=(f"Dimensions: {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm    |    "
                  f"Volume: {self.analysis['volume_cm3']:.1f} cm^3    |    "
                  f"Triangles: {self.analysis['triangle_count']:,}    |    "
                  f"Parts: {self.object_count if self.object_count else 1}")
        )

        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, posting["title"])

        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", posting["description"])

        self.category_entry.delete(0, "end")
        self.category_entry.insert(0, posting["category"])

        self.tags_entry.delete("1.0", "end")
        self.tags_entry.insert("1.0", ", ".join(posting["tags"]))

    def copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text.strip())
        messagebox.showinfo("Copied", "Copied to clipboard.")

    def save_all(self):
        if not self.analysis:
            messagebox.showwarning("Nothing to save", "Generate a posting first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
            initialfile="makerworld_posting.txt",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("TITLE\n")
            f.write(self.title_entry.get() + "\n\n")
            f.write("CATEGORY\n")
            f.write(self.category_entry.get() + "\n\n")
            f.write("TAGS\n")
            f.write(self.tags_entry.get("1.0", "end").strip() + "\n\n")
            f.write("DESCRIPTION\n")
            f.write(self.desc_text.get("1.0", "end").strip() + "\n")
        messagebox.showinfo("Saved", f"Saved to {path}")

    def open_makerworld(self):
        import webbrowser
        webbrowser.open("https://makerworld.com/en/upload")


if __name__ == "__main__":
    app = App()
    app.mainloop()
