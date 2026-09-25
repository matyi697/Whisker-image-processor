import os

os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

import sys
import argparse
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

INFO_BAR_RATIO = 0.08  # Az alsó paramétersor aránya


class ZoomPanCanvas(tk.Canvas):
    """Interaktív nagyítható, mozgatható és RAJZOLHATÓ vászon"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.image_bgr = None
        self.zoom_scale = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.tk_img = None

        # Manuális maszkok
        self.mask_exclude = None
        self.mask_protect = None

        # Ecset beállítások
        self.app_mode = "pan"  # 'pan', 'erase', 'protect'
        self.brush_radius = 15
        self.draw_points = []
        self.on_mask_updated = None  # Callback függvény

        # Egéresemények
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<MouseWheel>", self.on_zoom)  # Windows
        self.bind("<Button-4>", lambda e: self.on_zoom(e, 1.15))  # Linux fel
        self.bind("<Button-5>", lambda e: self.on_zoom(e, 0.85))  # Linux le
        self.bind("<Double-Button-1>", self.reset_view)
        self.bind("<Configure>", lambda e: self.render())

    def init_masks(self, shape):
        self.mask_exclude = np.zeros(shape[:2], dtype=np.uint8)
        self.mask_protect = np.zeros(shape[:2], dtype=np.uint8)

    def set_image(self, bgr_img):
        self.image_bgr = bgr_img
        if self.mask_exclude is None:
            self.init_masks(bgr_img.shape)
        self.render()

    def reset_view(self, event=None):
        self.zoom_scale = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.render()

    def get_img_coords(self, cx, cy):
        if self.image_bgr is None:
            return None, None
        cw, ch = self.winfo_width(), self.winfo_height()
        ih, iw = self.image_bgr.shape[:2]
        base_scale = min(cw / iw, ch / ih)
        cur_scale = base_scale * self.zoom_scale

        nw, nh = max(1, int(iw * cur_scale)), max(1, int(ih * cur_scale))
        x_center = cw // 2 + self.pan_x
        y_center = ch // 2 + self.pan_y
        x_tl = x_center - nw // 2
        y_tl = y_center - nh // 2

        img_x = int((cx - x_tl) / cur_scale)
        img_y = int((cy - y_tl) / cur_scale)

        img_x = max(0, min(iw - 1, img_x))
        img_y = max(0, min(ih - 1, img_y))
        return img_x, img_y

    def on_press(self, event):
        if self.app_mode == "pan":
            self.drag_start_x = event.x
            self.drag_start_y = event.y
        else:
            img_x, img_y = self.get_img_coords(event.x, event.y)
            if img_x is not None:
                self.draw_points = [(img_x, img_y)]

    def on_drag(self, event):
        if self.app_mode == "pan":
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.pan_x += dx
            self.pan_y += dy
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.render()
        else:
            img_x, img_y = self.get_img_coords(event.x, event.y)
            if img_x is not None:
                self.draw_points.append((img_x, img_y))
                # Ideiglenes vizuális visszajelzés rajzolása a vászonra
                r = self.brush_radius * self.zoom_scale
                color = "red" if self.app_mode == "erase" else "blue"
                self.create_oval(
                    event.x - r,
                    event.y - r,
                    event.x + r,
                    event.y + r,
                    fill=color,
                    outline=color,
                    tags="temp_draw",
                )

    def on_release(self, event):
        if self.app_mode != "pan" and self.draw_points:
            color = 255
            thickness = int(self.brush_radius * 2)

            target_mask = (
                self.mask_exclude if self.app_mode == "erase" else self.mask_protect
            )
            clear_mask = (
                self.mask_protect if self.app_mode == "erase" else self.mask_exclude
            )

            for i in range(len(self.draw_points) - 1):
                p1 = self.draw_points[i]
                p2 = self.draw_points[i + 1]
                cv2.line(target_mask, p1, p2, color, thickness)
                cv2.line(
                    clear_mask, p1, p2, 0, thickness
                )  # A másik maszkról letöröljük

            if len(self.draw_points) == 1:
                cv2.circle(
                    target_mask, self.draw_points[0], self.brush_radius, color, -1
                )
                cv2.circle(clear_mask, self.draw_points[0], self.brush_radius, 0, -1)

            self.delete("temp_draw")
            self.draw_points = []

            if self.on_mask_updated:
                self.on_mask_updated()

    def on_zoom(self, event, factor=None):
        if factor is None:
            factor = 1.15 if event.delta > 0 else 0.85
        new_scale = self.zoom_scale * factor
        if 0.2 <= new_scale <= 25.0:
            self.pan_x = int(event.x - (event.x - self.pan_x) * factor)
            self.pan_y = int(event.y - (event.y - self.pan_y) * factor)
            self.zoom_scale = new_scale
            self.render()

    def render(self):
        if self.image_bgr is None:
            return
        cw, ch = self.winfo_width(), self.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        ih, iw = self.image_bgr.shape[:2]
        base_scale = min(cw / iw, ch / ih)
        cur_scale = base_scale * self.zoom_scale

        nw = max(1, int(iw * cur_scale))
        nh = max(1, int(ih * cur_scale))

        resized = cv2.resize(self.image_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        self.tk_img = ImageTk.PhotoImage(image=pil_img)

        self.delete("all")
        x_center = cw // 2 + self.pan_x
        y_center = ch // 2 + self.pan_y
        self.create_image(x_center, y_center, anchor=tk.CENTER, image=self.tk_img)


class SEMStudioApp:
    def __init__(self, root, image_path, field_width_um):
        self.root = root
        self.image_path = image_path
        self.field_width_um = field_width_um

        self.root.title(
            f"SEM Stúdió (Kézi Felülbírálással) - [{os.path.basename(self.image_path)}]"
        )
        self.root.geometry("1480x920")

        self.img_raw = cv2.imread(self.image_path, cv2.IMREAD_GRAYSCALE)
        if self.img_raw is None:
            raise FileNotFoundError(
                f"Nem sikerült betölteni a képet: {self.image_path}"
            )

        h_orig, w_orig = self.img_raw.shape
        self.crop_h = int(h_orig * (1.0 - INFO_BAR_RATIO))
        self.roi = self.img_raw[: self.crop_h, :]
        self.info_bar = self.img_raw[self.crop_h :, :]

        self.pixel_size_um = self.field_width_um / w_orig
        self.pixel_area_um2 = self.pixel_size_um**2
        self.bg_median = int(np.median(self.roi))

        self.latest_display_bgr = None
        self.last_stats = (0, [])
        self._update_job = None

        self.left_container = ttk.Frame(root, width=450)
        self.left_container.pack(side=tk.LEFT, fill=tk.Y)
        self.left_container.pack_propagate(False)

        self.canvas_scroll = tk.Canvas(self.left_container, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self.left_container, orient=tk.VERTICAL, command=self.canvas_scroll.yview
        )
        self.controls_frame = ttk.Frame(self.canvas_scroll, padding=10)

        self.controls_frame.bind(
            "<Configure>",
            lambda e: self.canvas_scroll.configure(
                scrollregion=self.canvas_scroll.bbox("all")
            ),
        )
        self.canvas_scroll.create_window(
            (0, 0), window=self.controls_frame, anchor="nw"
        )
        self.canvas_scroll.configure(xscrollcommand=self.scrollbar.set)
        self.canvas_scroll.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.right_frame = ttk.Frame(root)
        self.right_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        nav_info = ttk.Label(
            self.right_frame,
            text=f"📁 {os.path.basename(self.image_path)} | 💡 Görgő: Zoom | Egér húzás: Mozgás/Rajzolás mód szerint",
            font=("Arial", 9, "italic"),
        )
        nav_info.pack(side=tk.TOP, anchor=tk.W, padx=8, pady=4)

        self.zoom_canvas = ZoomPanCanvas(self.right_frame, bg="#1a1a1a")
        self.zoom_canvas.pack(fill=tk.BOTH, expand=True)
        self.zoom_canvas.on_mask_updated = self.trigger_update

        self._build_all_controls()
        self.update_pipeline()

    def _build_all_controls(self):
        # 0. KÉZI FELÜLBÍRÁLÁS (MANUAL OVERRIDE)
        draw_box = ttk.LabelFrame(
            self.controls_frame, text="Manuális Javítás (Ecset / Radír)", padding=8
        )
        draw_box.pack(fill=tk.X, pady=4)

        self.app_mode_var = tk.StringVar(value="pan")

        def on_mode_change():
            self.zoom_canvas.app_mode = self.app_mode_var.get()

        ttk.Radiobutton(
            draw_box,
            text="Navigáció (Kép mozgatása)",
            variable=self.app_mode_var,
            value="pan",
            command=on_mode_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            draw_box,
            text="Radír (Téves foltok kizárása)",
            variable=self.app_mode_var,
            value="erase",
            command=on_mode_change,
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            draw_box,
            text="Védő (Karc alóli felmentés)",
            variable=self.app_mode_var,
            value="protect",
            command=on_mode_change,
        ).pack(anchor=tk.W)

        self.scale_brush = self._add_slider(
            draw_box, "Ecset vastagsága (px):", 1, 100, 15, 1, is_brush=True
        )

        def clear_manual_masks():
            if self.zoom_canvas.mask_exclude is not None:
                self.zoom_canvas.mask_exclude.fill(0)
                self.zoom_canvas.mask_protect.fill(0)
                self.trigger_update()

        ttk.Button(
            draw_box, text="🧹 Kézi rajzok törlése (Reset)", command=clear_manual_masks
        ).pack(fill=tk.X, pady=4)

        # 1. NÉZET MÓDOK
        view_box = ttk.LabelFrame(
            self.controls_frame, text="Nézet és Megjelenítés", padding=8
        )
        view_box.pack(fill=tk.X, pady=4)

        self.var_show_raw = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            view_box,
            text="Eredeti tiszta kép (Overlay KI)",
            variable=self.var_show_raw,
            command=self.trigger_update,
        ).pack(anchor=tk.W, pady=2)

        self.var_show_scratches = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            view_box,
            text="Detektált karcok mutatása (Piros sáv)",
            variable=self.var_show_scratches,
            command=self.trigger_update,
        ).pack(anchor=tk.W, pady=2)

        self.var_show_manual = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            view_box,
            text="Kézi ecset-zónák mutatása (Halvány szín)",
            variable=self.var_show_manual,
            command=self.trigger_update,
        ).pack(anchor=tk.W, pady=2)

        # 2. KÉPKORREKCIÓ
        img_box = ttk.LabelFrame(self.controls_frame, text="Képkorrekció", padding=8)
        img_box.pack(fill=tk.X, pady=4)
        self.scale_contrast = self._add_slider(
            img_box, "Kontraszt:", 0.5, 3.5, 1.3, 0.1
        )
        self.scale_brightness = self._add_slider(img_box, "Fényerő:", -80, 80, 0, 1)

        # 3. FEHÉR PÁCÁK DETEKTÁLÁSA
        paca_box = ttk.LabelFrame(
            self.controls_frame, text="Fehér Pácák Keresése", padding=8
        )
        paca_box.pack(fill=tk.X, pady=4)
        self.scale_thresh = self._add_slider(
            paca_box, "Fehérség küszöb (Threshold):", 50, 255, 195, 1
        )
        self.scale_min_area = self._add_slider(
            paca_box, "Min. Páca Méret (px):", 1, 100, 8, 1
        )
        self.scale_max_area = self._add_slider(
            paca_box, "Max. Páca Méret (px):", 50, 3000, 1000, 10
        )

        # 4. HOUGH EGYENES KARC DETEKTÁLÁS + ÁRNYÉK VALIDÁCIÓ
        karc_box = ttk.LabelFrame(
            self.controls_frame, text="Karc Kizárás & Árnyék Validáció", padding=8
        )
        karc_box.pack(fill=tk.X, pady=4)

        self.var_enable_scratch_excl = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            karc_box,
            text="⚡ KARC DETEKTÁLÁS BEKAPCSOLVA",
            variable=self.var_enable_scratch_excl,
            command=self.trigger_update,
        ).pack(anchor=tk.W, pady=3)

        self.scale_min_line = self._add_slider(
            karc_box, "Min. Karc Hossz (px):", 30, 800, 160, 5
        )
        self.scale_max_gap = self._add_slider(
            karc_box, "Karc folytonossági hézag (Max Gap):", 1, 100, 25, 1
        )
        self.scale_hough_th = self._add_slider(
            karc_box, "Hough merevségi küszöb:", 10, 300, 75, 5
        )
        self.scale_canny_low = self._add_slider(
            karc_box, "Élkereső alsó küszöb:", 5, 200, 35, 1
        )
        self.scale_canny_high = self._add_slider(
            karc_box, "Élkereső felső küszöb:", 20, 350, 95, 1
        )

        self.scale_shadow_th = self._add_slider(
            karc_box, "Árnyék (low point) max fényessége:", 10, 150, 70, 1
        )
        self.scale_shadow_dist = self._add_slider(
            karc_box, "Árnyék max távolsága a vonaltól (px):", 1, 20, 6, 1
        )
        self.scale_band_width = self._add_slider(
            karc_box, "Karc sáv kizárási vastagság (px):", 1, 35, 5, 1
        )

        # 5. PÁCA VÉDELEM
        protect_box = ttk.LabelFrame(
            self.controls_frame, text="Karcban Ülő Pácák Védelme", padding=8
        )
        protect_box.pack(fill=tk.X, pady=4)
        self.scale_spot_th = self._add_slider(
            protect_box, "Védendő fehér folt küszöb:", 80, 255, 195, 1
        )
        self.scale_spot_dilate = self._add_slider(
            protect_box, "Folt védelmi puffer (px):", 1, 15, 3, 1
        )

        # 6. STATISZTIKA DOBOZ
        stat_box = ttk.LabelFrame(
            self.controls_frame, text="Mérési Eredmények", padding=8
        )
        stat_box.pack(fill=tk.X, pady=6)
        self.lbl_count = ttk.Label(
            stat_box,
            text="Pácák száma: - db",
            font=("Arial", 10, "bold"),
            foreground="green",
        )
        self.lbl_count.pack(anchor=tk.W)
        self.lbl_area_avg = ttk.Label(stat_box, text="Átlagos terület: - µm²")
        self.lbl_area_avg.pack(anchor=tk.W)
        self.lbl_area_min = ttk.Label(stat_box, text="Min. terület: - µm²")
        self.lbl_area_min.pack(anchor=tk.W)
        self.lbl_area_max = ttk.Label(stat_box, text="Max. terület: - µm²")
        self.lbl_area_max.pack(anchor=tk.W)

        # 7. MENTÉSI GOMBOK
        save_box = ttk.LabelFrame(self.controls_frame, text="Fájl Mentése", padding=8)
        save_box.pack(fill=tk.X, pady=6)
        ttk.Button(
            save_box,
            text="💾 Jelölt Eredménykép Mentése (TIF/PNG)",
            command=self.save_annotated_image,
        ).pack(fill=tk.X, pady=3)
        ttk.Button(
            save_box,
            text="📄 Statisztika Exportálása (TXT)",
            command=self.export_stats_txt,
        ).pack(fill=tk.X, pady=3)

    def _add_slider(
        self, parent, label_text, from_val, to_val, default_val, step, is_brush=False
    ):
        lbl = ttk.Label(parent, text=f"{label_text} {default_val}")
        lbl.pack(anchor=tk.W)

        def on_slide(val):
            val_f = float(val)
            formatted = f"{val_f:.1f}" if step < 1 else f"{int(val_f)}"
            lbl.config(text=f"{label_text} {formatted}")

            if is_brush:
                self.zoom_canvas.brush_radius = int(val_f)
            else:
                if self._update_job is not None:
                    self.root.after_cancel(self._update_job)
                self._update_job = self.root.after(150, self.update_pipeline)

        slider = ttk.Scale(
            parent, from_=from_val, to=to_val, value=default_val, command=on_slide
        )
        slider.pack(fill=tk.X, pady=(0, 4))
        return slider

    def trigger_update(self):
        if self._update_job is not None:
            self.root.after_cancel(self._update_job)
        self.update_pipeline()

    def update_pipeline(self):
        self._update_job = None

        # Alap paraméterek
        contrast = float(self.scale_contrast.get())
        brightness = float(self.scale_brightness.get())
        thresh_val = int(float(self.scale_thresh.get()))
        min_area = int(float(self.scale_min_area.get()))
        max_area = int(float(self.scale_max_area.get()))

        # Nyers nézet
        if self.var_show_raw.get():
            disp = cv2.cvtColor(self.roi, cv2.COLOR_GRAY2BGR)
            self.latest_display_bgr = disp
            self.zoom_canvas.set_image(disp)
            self.lbl_count.config(text="Eredeti tiszta kép megjelenítve")
            return

        adjusted = cv2.convertScaleAbs(self.roi, alpha=contrast, beta=brightness)
        disp_bgr = cv2.cvtColor(adjusted, cv2.COLOR_GRAY2BGR)

        # Kézi maszkok betöltése a vászonról
        manual_exclude = self.zoom_canvas.mask_exclude
        manual_protect = self.zoom_canvas.mask_protect

        # --- ALGORITMIKUS KARC KIZÁRÁS ---
        scratch_exclusion_mask = np.zeros_like(self.roi, dtype=np.uint8)
        if self.var_enable_scratch_excl.get():
            min_l = int(float(self.scale_min_line.get()))
            max_g = int(float(self.scale_max_gap.get()))
            hough_th = int(float(self.scale_hough_th.get()))
            c_low = int(float(self.scale_canny_low.get()))
            c_high = int(float(self.scale_canny_high.get()))

            shadow_th = int(float(self.scale_shadow_th.get()))
            shadow_dist = int(float(self.scale_shadow_dist.get()))
            band_w = int(float(self.scale_band_width.get()))

            spot_th = int(float(self.scale_spot_th.get()))
            spot_buf = int(float(self.scale_spot_dilate.get()))

            # Árnyék maszk
            _, shadow_mask = cv2.threshold(
                adjusted, shadow_th, 255, cv2.THRESH_BINARY_INV
            )
            kernel_shadow = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * shadow_dist + 1, 2 * shadow_dist + 1)
            )
            shadow_dilated = cv2.dilate(shadow_mask, kernel_shadow)

            # Vonalak
            blurred = cv2.GaussianBlur(adjusted, (3, 3), 0)
            edges = cv2.Canny(blurred, c_low, c_high)
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=hough_th,
                minLineLength=min_l,
                maxLineGap=max_g,
            )

            scratch_lines_raw = np.zeros_like(self.roi, dtype=np.uint8)
            if lines is not None:
                reshaped = lines.reshape(-1, 4)
                for x1, y1, x2, y2 in reshaped:
                    cv2.line(
                        scratch_lines_raw,
                        (int(x1), int(y1)),
                        (int(x2), int(y2)),
                        255,
                        thickness=1,
                    )

            # Validálás és kiterjesztés
            validated_scratches = cv2.bitwise_and(scratch_lines_raw, shadow_dilated)
            kernel_band = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (band_w, band_w))
            scratch_exclusion_base = cv2.dilate(validated_scratches, kernel_band)

            # Automatikus páca védelem
            _, spots_bin = cv2.threshold(self.roi, spot_th, 255, cv2.THRESH_BINARY)
            kernel_buf = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * spot_buf + 1, 2 * spot_buf + 1)
            )
            protected_spots = cv2.dilate(spots_bin, kernel_buf, iterations=1)

            scratch_exclusion_mask = cv2.bitwise_and(
                scratch_exclusion_base, cv2.bitwise_not(protected_spots)
            )

        # --- FEHÉR PÁCÁK VIZSGÁLATA ---
        blurred_spots = cv2.GaussianBlur(adjusted, (3, 3), 0)
        _, binary_spots = cv2.threshold(
            blurred_spots, thresh_val, 255, cv2.THRESH_BINARY
        )
        contours, _ = cv2.findContours(
            binary_spots, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        valid_areas_um2 = []
        for cnt in contours:
            area_px = cv2.contourArea(cnt)
            if not (min_area <= area_px <= max_area):
                continue

            mask_cnt = np.zeros_like(self.roi, dtype=np.uint8)
            cv2.drawContours(mask_cnt, [cnt], -1, 255, -1)
            cnt_area = np.count_nonzero(mask_cnt) + 1e-5

            # 1. Kézi radír ellenőrzése
            if manual_exclude is not None:
                overlap_exclude = cv2.bitwise_and(mask_cnt, manual_exclude)
                if np.count_nonzero(overlap_exclude) / cnt_area > 0.40:
                    continue  # Kézzel letörölve

            # 2. Kézi védelem ellenőrzése
            is_manually_protected = False
            if manual_protect is not None:
                overlap_protect = cv2.bitwise_and(mask_cnt, manual_protect)
                if np.count_nonzero(overlap_protect) / cnt_area > 0.40:
                    is_manually_protected = True

            # 3. Gépi karc-kizárás (ha nincs kézzel védve)
            if self.var_enable_scratch_excl.get() and not is_manually_protected:
                overlap_scratch = cv2.bitwise_and(mask_cnt, scratch_exclusion_mask)
                if np.count_nonzero(overlap_scratch) / cnt_area > 0.40:
                    continue

            # Ha mindenen átment: Érvényes páca!
            area_um2 = area_px * self.pixel_area_um2
            valid_areas_um2.append(area_um2)
            cv2.drawContours(disp_bgr, [cnt], -1, (0, 255, 0), 2)

        # --- MEGJELENÍTÉSI RÉTEGEK RÁRAJZOLÁSA ---

        # 1. Automata Karcok (Piros)
        if self.var_enable_scratch_excl.get() and self.var_show_scratches.get():
            disp_bgr[scratch_exclusion_mask > 0] = [0, 0, 220]

        # 2. Manuális Maszkok (Halvány Piros és Kék)
        if self.var_show_manual.get():
            if manual_exclude is not None:
                # Kézi radír (Halvány piros)
                overlay = disp_bgr.copy()
                overlay[manual_exclude > 0] = [0, 0, 255]
                cv2.addWeighted(overlay, 0.4, disp_bgr, 0.6, 0, disp_bgr)

            if manual_protect is not None:
                # Kézi védelem (Halvány kék)
                overlay = disp_bgr.copy()
                overlay[manual_protect > 0] = [255, 100, 0]
                cv2.addWeighted(overlay, 0.4, disp_bgr, 0.6, 0, disp_bgr)

        # --- STATISZTIKA ---
        count = len(valid_areas_um2)
        self.last_stats = (count, valid_areas_um2)
        if count > 0:
            avg_a = np.mean(valid_areas_um2)
            min_a = np.min(valid_areas_um2)
            max_a = np.max(valid_areas_um2)
            self.lbl_count.config(text=f"Talált pácák: {count} db")
            self.lbl_area_avg.config(text=f"Átlagos terület: {avg_a:.2f} µm²")
            self.lbl_area_min.config(text=f"Min. terület: {min_a:.2f} µm²")
            self.lbl_area_max.config(text=f"Max. terület: {max_a:.2f} µm²")
        else:
            self.lbl_count.config(text="Talált pácák: 0 db")
            self.lbl_area_avg.config(text="Átlagos terület: - µm²")
            self.lbl_area_min.config(text="Min. terület: - µm²")
            self.lbl_area_max.config(text="Max. terület: - µm²")

        self.latest_display_bgr = disp_bgr
        self.zoom_canvas.set_image(disp_bgr)

    def save_annotated_image(self):
        if self.latest_display_bgr is None:
            return
        out_path = filedialog.asksaveasfilename(
            defaultextension=".tif",
            filetypes=[
                ("TIFF kép", "*.tif"),
                ("PNG kép", "*.png"),
                ("JPG kép", "*.jpg"),
            ],
        )
        if not out_path:
            return
        info_bgr = cv2.cvtColor(self.info_bar, cv2.COLOR_GRAY2BGR)
        full_res = np.vstack((self.latest_display_bgr, info_bgr))
        cv2.imwrite(out_path, full_res)
        messagebox.showinfo("Sikeres Mentés", f"A kép elmentve:\n{out_path}")

    def export_stats_txt(self):
        count, areas = self.last_stats
        if count == 0:
            messagebox.showwarning("Figyelmeztetés", "Nincs mért páca a képen!")
            return
        out_path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Szöveges fájl", "*.txt")]
        )
        if not out_path:
            return

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("SEM FOLT ÉS PÁCA MÉRÉSI JEGYZŐKÖNYV\n")
            f.write("=" * 45 + "\n")
            f.write(f"Képfájl: {self.image_path}\n")
            f.write(f"Látómező szélesség: {self.field_width_um} µm\n")
            f.write(f"Összes talált páca: {count} db\n")
            f.write(f"Átlagos terület: {np.mean(areas):.4f} µm²\n")
            f.write(f"Minimum terület: {np.min(areas):.4f} µm²\n")
            f.write(f"Maximum terület: {np.max(areas):.4f} µm²\n")
            f.write("-" * 45 + "\n")
            f.write("Egyedi pácák területe (µm²):\n")
            for idx, a in enumerate(areas, 1):
                f.write(f"{idx}. folt: {a:.4f} µm²\n")
        messagebox.showinfo("Export Kész", f"A jegyzőkönyv elmentve:\n{out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="SEM mikroszkópos folt- és karc elemző stúdió"
    )
    parser.add_argument(
        "image",
        nargs="?",
        default="test.tif",
        help="A feldolgozandó TIF képfájl elérési útja",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=float,
        default=120.0,
        help="A kép látómezejének szélessége mikrométerben",
    )

    args = parser.parse_args()
    if not os.path.exists(args.image):
        print(f"Hiba: A megadott képfájl nem található: '{args.image}'")
        sys.exit(1)

    root = tk.Tk()
    app = SEMStudioApp(root, image_path=args.image, field_width_um=args.width)
    root.mainloop()


if __name__ == "__main__":
    main()
