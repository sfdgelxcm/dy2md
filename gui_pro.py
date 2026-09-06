"""
Video to Markdown - Pro UI
参考 SD-WebUI-Forge 风格的深色卡片式界面
"""
import os
import sys
import asyncio
import threading
import yaml
from typing import Optional, Sequence

import customtkinter as ctk  # type: ignore
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(__file__))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Theme:
    """SD-WebUI-Forge 风格配色"""
    BG = '#1a1a1a'
    CARD = '#2a2a2a'
    CARD_HOVER = '#333333'
    BORDER = '#3a3a3a'
    
    ACCENT = '#3b82f6'
    ACCENT_HOVER = '#60a5fa'
    
    TEXT = '#ffffff'
    TEXT_SECONDARY = '#a0a0a0'
    TEXT_MUTED = '#666666'
    
    SUCCESS = '#22c55e'
    ERROR = '#ef4444'


class FunctionCard(ctk.CTkFrame):
    """功能卡片组件"""
    def __init__(self, parent, icon: str, title: str, subtitle: str, command=None, selected=False):
        super().__init__(parent, fg_color=Theme.CARD, corner_radius=8,
                        border_width=1, border_color=Theme.BORDER)
        
        self.command = command
        self.selected = selected
        
        # 内容
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=14)
        
        # 图标 + 文字行
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x")
        
        # 图标
        icon_label = ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=18),
                                  text_color=Theme.TEXT_SECONDARY, width=24)
        icon_label.pack(side="left")
        
        # 文字
        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True, padx=(12, 0))
        
        title_label = ctk.CTkLabel(text_frame, text=title,
                                   font=ctk.CTkFont(size=14, weight="bold"),
                                   text_color=Theme.TEXT, anchor="w")
        title_label.pack(anchor="w")
        
        subtitle_label = ctk.CTkLabel(text_frame, text=subtitle,
                                      font=ctk.CTkFont(size=11),
                                      text_color=Theme.TEXT_MUTED, anchor="w")
        subtitle_label.pack(anchor="w")
        
        # 箭头
        arrow = ctk.CTkLabel(row, text=">", font=ctk.CTkFont(size=14),
                            text_color=Theme.TEXT_MUTED)
        arrow.pack(side="right")
        
        # 绑定点击
        for widget in [self, content, row, icon_label, text_frame, title_label, subtitle_label, arrow]:
            widget.bind("<Button-1>", self._on_click)
            widget.configure(cursor="hand2")
        
        if selected:
            self.configure(border_color=Theme.ACCENT)
    
    def _on_click(self, e):
        if self.command:
            self.command()
    
    def set_selected(self, selected: bool):
        self.selected = selected
        self.configure(border_color=Theme.ACCENT if selected else Theme.BORDER)


class ProVideoToMarkdownGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Video to Markdown")
        self.geometry("1200x760")
        self.minsize(1000, 680)
        self.configure(fg_color=Theme.BG)
        
        self.pipeline = None
        self.is_processing = False
        self.current_mode = "url"
        self.mode_cards = {}
        self.audio_files = []
        self.text_files = []
        self.batch_window = None
        self.batch_textbox = None
        self.batch_count_label = None
        self.audio_batch_window = None
        self.audio_batch_textbox = None
        self.audio_batch_count_label = None
        self.config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        self.raw_include_var = ctk.BooleanVar(value=self._load_raw_include())
        self.log_font_size = 11
        self.result_font_size = 12
        self.min_output_font_size = 10
        self.max_output_font_size = 28
        self.log_font = ctk.CTkFont(family="Consolas", size=self.log_font_size)
        self.result_font = ctk.CTkFont(size=self.result_font_size)
        
        self._create_ui()
        self._bind_output_shortcuts()
    
    def _create_ui(self):
        # 主布局：左侧功能区 + 右侧信息区
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=20)
        
        # 左侧
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        
        # 右侧
        right = ctk.CTkFrame(main, fg_color="transparent", width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        
        self._create_left_panel(left)
        self._create_right_panel(right)
    
    def _create_left_panel(self, parent):
        # 标题
        title = ctk.CTkLabel(parent, text="输入类型",
                            font=ctk.CTkFont(size=14, weight="bold"),
                            text_color=Theme.TEXT_SECONDARY)
        title.pack(anchor="w", pady=(0, 12))
        
        # 功能卡片网格
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 20))
        
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="col")
        
        modes = [
            ("url", "🔗", "抖音链接", "douyin-url"),
            ("audio", "🎵", "本地音频", "local-audio"),
            ("folder", "📁", "批量处理", "batch-folder"),
            ("text", "📝", "文本清洗", "text-clean"),
        ]
        
        for i, (mode, icon, title, subtitle) in enumerate(modes):
            card = FunctionCard(grid, icon, title, subtitle,
                               command=lambda m=mode: self._select_mode(m),
                               selected=(mode == "url"))
            card.grid(row=0, column=i, padx=6, pady=6, sticky="nsew")
            self.mode_cards[mode] = card
        
        # 分隔线
        sep = ctk.CTkFrame(parent, height=1, fg_color=Theme.BORDER)
        sep.pack(fill="x", pady=(0, 20))
        
        # 输入区域
        input_section = ctk.CTkFrame(parent, fg_color="transparent")
        input_section.pack(fill="x", pady=(0, 16))
        
        self.input_label = ctk.CTkLabel(input_section, text="视频链接",
                                        font=ctk.CTkFont(size=13),
                                        text_color=Theme.TEXT_SECONDARY)
        self.input_label.pack(anchor="w", pady=(0, 8))
        
        input_row = ctk.CTkFrame(input_section, fg_color="transparent")
        input_row.pack(fill="x")
        
        self.url_entry = ctk.CTkEntry(input_row, height=42,
                                      placeholder_text="请粘贴抖音视频链接或分享文本...",
                                      font=ctk.CTkFont(size=13),
                                      fg_color=Theme.CARD,
                                      border_color=Theme.BORDER,
                                      text_color=Theme.TEXT)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.browse_btn = ctk.CTkButton(input_row, text="浏览", width=70, height=42,
                                        font=ctk.CTkFont(size=13),
                                        fg_color=Theme.CARD,
                                        hover_color=Theme.CARD_HOVER,
                                        border_width=1, border_color=Theme.BORDER,
                                        command=self._browse_file)

        # 音频多选信息区域（用于本地音频模式）
        self.audio_multi_section = ctk.CTkFrame(parent, fg_color="transparent")

        audio_header = ctk.CTkFrame(self.audio_multi_section, fg_color="transparent")
        audio_header.pack(fill="x", pady=(12, 0))

        self.audio_files_label = ctk.CTkLabel(audio_header, text="未选择文件",
                                              font=ctk.CTkFont(size=11),
                                              text_color=Theme.TEXT_MUTED, anchor="w", justify="left",
                                              wraplength=520)
        self.audio_files_label.pack(side="left", anchor="w")

        self.manage_audio_files_btn = ctk.CTkButton(audio_header, text="批量管理",
                                                    width=90, height=26,
                                                    font=ctk.CTkFont(size=11),
                                                    fg_color=Theme.CARD,
                                                    hover_color=Theme.CARD_HOVER,
                                                    border_width=1, border_color=Theme.BORDER,
                                                    command=self._open_audio_batch_window)
        self.manage_audio_files_btn.pack(side="right")
        
        # 文本输入区域（用于文本清洗模式）
        self.text_input_section = ctk.CTkFrame(parent, fg_color="transparent")

        files_header = ctk.CTkFrame(self.text_input_section, fg_color="transparent")
        files_header.pack(fill="x", pady=(0, 8))

        self.text_files_label = ctk.CTkLabel(files_header, text="未选择文件",
                                             font=ctk.CTkFont(size=11),
                                             text_color=Theme.TEXT_MUTED, anchor="w", justify="left",
                                             wraplength=520)
        self.text_files_label.pack(side="left", anchor="w")

        self.manage_text_files_btn = ctk.CTkButton(files_header, text="批量管理",
                                                   width=90, height=26,
                                                   font=ctk.CTkFont(size=11),
                                                   fg_color=Theme.CARD,
                                                   hover_color=Theme.CARD_HOVER,
                                                   border_width=1, border_color=Theme.BORDER,
                                                   command=self._open_text_batch_window)
        self.manage_text_files_btn.pack(side="right")
        
        text_label = ctk.CTkLabel(self.text_input_section, text="或直接粘贴文本内容",
                                  font=ctk.CTkFont(size=13),
                                  text_color=Theme.TEXT_SECONDARY)
        text_label.pack(anchor="w", pady=(0, 8))
        
        self.text_input = ctk.CTkTextbox(self.text_input_section, height=120,
                                         font=ctk.CTkFont(size=12),
                                         fg_color=Theme.CARD,
                                         border_color=Theme.BORDER,
                                         text_color=Theme.TEXT)
        self.text_input.pack(fill="both", expand=True)
        
        # 进度区域
        progress_section = ctk.CTkFrame(parent, fg_color="transparent")
        progress_section.pack(fill="x", pady=(0, 16))
        
        progress_header = ctk.CTkFrame(progress_section, fg_color="transparent")
        progress_header.pack(fill="x", pady=(0, 8))
        
        self.status_label = ctk.CTkLabel(progress_header, text="就绪",
                                         font=ctk.CTkFont(size=12),
                                         text_color=Theme.TEXT_SECONDARY,
                                         anchor="w")
        self.status_label.pack(side="left")
        
        self.progress_pct = ctk.CTkLabel(progress_header, text="",
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color=Theme.ACCENT)
        self.progress_pct.pack(side="right")
        
        self.progress_bar = ctk.CTkProgressBar(progress_section, height=6,
                                               fg_color=Theme.CARD,
                                               progress_color=Theme.ACCENT)
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)
        
        # 日志/结果区域
        output_section = ctk.CTkFrame(parent, fg_color="transparent")
        output_section.pack(fill="both", expand=True)
        
        self.tabview = ctk.CTkTabview(output_section, height=250,
                                      fg_color=Theme.CARD,
                                      segmented_button_fg_color=Theme.BG,
                                      segmented_button_selected_color=Theme.CARD,
                                      segmented_button_unselected_color=Theme.BG,
                                      corner_radius=8)
        self.tabview.pack(fill="both", expand=True)
        
        log_tab = self.tabview.add("日志")
        self.log_text = ctk.CTkTextbox(log_tab, font=self.log_font,
                                       fg_color="transparent", text_color=Theme.TEXT_SECONDARY,
                                       wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)
        
        result_tab = self.tabview.add("结果")
        self.result_text = ctk.CTkTextbox(result_tab, font=self.result_font,
                                          fg_color="transparent", text_color=Theme.TEXT,
                                          wrap="word")
        self.result_text.pack(fill="both", expand=True, padx=8, pady=8)
        
        # 底部信息
        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.pack(fill="x", pady=(12, 0))
        
        ver_label = ctk.CTkLabel(footer, text="版本: 1.1.0",
                                 font=ctk.CTkFont(size=11),
                                 text_color=Theme.TEXT_MUTED)
        ver_label.pack(side="left")
        
        fmt_label = ctk.CTkLabel(footer, text="支持: mp3, wav, m4a, flac, mp4, txt, md",
                                 font=ctk.CTkFont(size=11),
                                 text_color=Theme.TEXT_MUTED)
        fmt_label.pack(side="left", padx=(20, 0))
    
    def _create_right_panel(self, parent):
        title = ctk.CTkLabel(parent, text="操作",
                            font=ctk.CTkFont(size=14, weight="bold"),
                            text_color=Theme.TEXT_SECONDARY)
        title.pack(anchor="w", pady=(0, 12))
        
        notice_card = ctk.CTkFrame(parent, fg_color=Theme.CARD, corner_radius=8,
                                   border_width=1, border_color=Theme.BORDER)
        notice_card.pack(fill="x", pady=(0, 16))
        
        notice_inner = ctk.CTkFrame(notice_card, fg_color="transparent")
        notice_inner.pack(fill="x", padx=16, pady=14)
        
        notice_text = ctk.CTkLabel(notice_inner,
                                   text="1. 选择输入类型\n2. 输入链接或选择文件\n3. 点击一键处理\n4. 等待处理完成\n5. Ctrl+滚轮缩放日志/结果",
                                   font=ctk.CTkFont(size=12),
                                   text_color=Theme.TEXT_SECONDARY, justify="left")
        notice_text.pack(anchor="w")
        
        # 抖音URL格式示例
        url_card = ctk.CTkFrame(parent, fg_color=Theme.CARD, corner_radius=8,
                                border_width=1, border_color=Theme.BORDER)
        url_card.pack(fill="x", pady=(0, 16))
        
        url_inner = ctk.CTkFrame(url_card, fg_color="transparent")
        url_inner.pack(fill="x", padx=16, pady=14)
        
        url_title = ctk.CTkLabel(url_inner, text="支持的抖音链接格式",
                                 font=ctk.CTkFont(size=12, weight="bold"),
                                 text_color=Theme.TEXT)
        url_title.pack(anchor="w", pady=(0, 8))
        
        url_examples = ctk.CTkLabel(url_inner,
                                    text="• https://v.douyin.com/xxxxx/\n• https://www.douyin.com/video/xxxxx\n• 分享文本中包含的链接",
                                    font=ctk.CTkFont(size=11),
                                    text_color=Theme.TEXT_MUTED, justify="left")
        url_examples.pack(anchor="w")

        options_card = ctk.CTkFrame(parent, fg_color=Theme.CARD, corner_radius=8,
                                    border_width=1, border_color=Theme.BORDER)
        options_card.pack(fill="x", pady=(0, 16))

        options_inner = ctk.CTkFrame(options_card, fg_color="transparent")
        options_inner.pack(fill="x", padx=16, pady=12)

        options_title = ctk.CTkLabel(options_inner, text="RAW 输出",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color=Theme.TEXT)
        options_title.pack(anchor="w", pady=(0, 6))

        self.raw_timestamp_checkbox = ctk.CTkCheckBox(
            options_inner,
            text="保留时间戳",
            variable=self.raw_include_var,
            command=self._toggle_raw_timestamps,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            text_color=Theme.TEXT_SECONDARY,
            checkbox_width=18,
            checkbox_height=18,
        )
        self.raw_timestamp_checkbox.pack(anchor="w")
        
        self.start_btn = ctk.CTkButton(parent, text="▶  一键处理",
                                       font=ctk.CTkFont(size=16, weight="bold"),
                                       height=50, corner_radius=8,
                                       fg_color=Theme.ACCENT, hover_color=Theme.ACCENT_HOVER,
                                       command=self._start_processing)
        self.start_btn.pack(fill="x", pady=(0, 16))
        
        self.copy_btn = ctk.CTkButton(parent, text="复制结果", height=36,
                                      font=ctk.CTkFont(size=12), fg_color=Theme.CARD,
                                      hover_color=Theme.CARD_HOVER, border_width=1,
                                      border_color=Theme.BORDER, command=self._copy_result, state="disabled")
        self.copy_btn.pack(fill="x", pady=(0, 8))
        
        self.save_btn = ctk.CTkButton(parent, text="另存为", height=36,
                                      font=ctk.CTkFont(size=12), fg_color=Theme.CARD,
                                      hover_color=Theme.CARD_HOVER, border_width=1,
                                      border_color=Theme.BORDER, command=self._save_result, state="disabled")
        self.save_btn.pack(fill="x")
    
    def _load_raw_include(self) -> bool:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            return bool(config.get('raw', {}).get('include_timestamps', True))
        except Exception:
            return True

    def _persist_raw_include(self, include: bool):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return

        newline = "\n"
        for line in lines:
            if line.endswith("\r\n"):
                newline = "\r\n"
                break
            if line.endswith("\n"):
                newline = "\n"
                break

        raw_idx = None
        include_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("raw:"):
                raw_idx = i
                j = i + 1
                while j < len(lines):
                    stripped = lines[j].strip()
                    if stripped == "":
                        j += 1
                        continue
                    if lines[j].lstrip() == lines[j] and not stripped.startswith("#"):
                        break
                    if lines[j].lstrip().startswith("include_timestamps:"):
                        include_idx = j
                        break
                    j += 1
                break

        new_line = f"  include_timestamps: {'true' if include else 'false'}{newline}"

        if raw_idx is not None:
            if include_idx is not None:
                lines[include_idx] = new_line
            else:
                lines.insert(raw_idx + 1, new_line)
        else:
            insert_at = None
            for i, line in enumerate(lines):
                if line.strip().startswith("chunking:") and line.lstrip() == line:
                    insert_at = i
                    break
            block = [f"raw:{newline}", new_line, newline]
            if insert_at is None:
                if lines and lines[-1].strip() != "":
                    lines.append(newline)
                lines.extend(block)
            else:
                if insert_at > 0 and lines[insert_at - 1].strip() != "":
                    block.insert(0, newline)
                lines[insert_at:insert_at] = block

        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def _toggle_raw_timestamps(self):
        value = bool(self.raw_include_var.get())
        self._persist_raw_include(value)
        if self.pipeline is not None:
            self.pipeline.raw_include_timestamps = value

    def _select_mode(self, mode: str):
        self.current_mode = mode
        self.audio_files = []
        self.text_files = []
        if mode != "text":
            self._close_batch_window()
        if mode != "audio":
            self._close_audio_batch_window()
        for m, card in self.mode_cards.items():
            card.set_selected(m == mode)
        config = {"url": ("视频链接", "请粘贴抖音视频链接或分享文本..."),
                  "audio": ("音频文件", "选择音频文件..."),
                  "folder": ("文件夹", "选择要处理的文件夹..."),
                  "text": ("文本文件", "选择文件或直接粘贴文本...")}
        label, placeholder = config[mode]
        self.input_label.configure(text=label)
        self.url_entry.configure(placeholder_text=placeholder)
        self.url_entry.delete(0, "end")
        
        # 显示/隐藏文本输入区域
        if mode == "text":
            self.browse_btn.pack(side="left", padx=(0, 10))
            self.audio_multi_section.pack_forget()
            self.text_input_section.pack(fill="x", pady=(16, 0))
            self._update_text_files_display()
            self.text_input.delete("1.0", "end")
        else:
            self.text_input_section.pack_forget()
            self.audio_multi_section.pack_forget()
            if mode == "url":
                self.browse_btn.pack_forget()
            else:
                self.browse_btn.pack(side="left", padx=(0, 10))

        if mode == "audio":
            self.audio_multi_section.pack(fill="x")
            self._update_audio_files_display()
    
    def _browse_file(self):
        if self.current_mode == "audio":
            self._pick_audio_files(append=False)
        elif self.current_mode == "text":
            self._pick_text_files(append=False)
        else:
            path = filedialog.askdirectory()
            if path:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, path)

    def _pick_audio_files(self, append: bool = False):
        paths = filedialog.askopenfilenames(filetypes=[("音频文件", "*.mp3 *.wav *.m4a *.flac *.ogg *.mp4"), ("所有文件", "*.*")])
        if not paths:
            return
        self._set_audio_files(paths, append=append)

    def _set_audio_files(self, paths: Sequence[str], append: bool = False):
        if append:
            existing = {os.path.normcase(p) for p in self.audio_files}
            for p in paths:
                key = os.path.normcase(p)
                if key not in existing:
                    self.audio_files.append(p)
                    existing.add(key)
        else:
            self.audio_files = list(paths)
        self._update_audio_files_display()

    def _clear_audio_files(self):
        self.audio_files = []
        self._update_audio_files_display()

    def _update_audio_files_display(self):
        if self.current_mode != "audio":
            return

        if not self.audio_files:
            self.audio_files_label.configure(text="未选择文件")
            self.url_entry.delete(0, "end")
        elif len(self.audio_files) == 1:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, self.audio_files[0])
            name = self._ellipsize(os.path.basename(self.audio_files[0]), max_len=40)
            self.audio_files_label.configure(text=f"已选择: {name}")
        else:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, f"已选择 {len(self.audio_files)} 个文件")
            self.audio_files_label.configure(text=f"已选择 {len(self.audio_files)} 个文件（点击“批量管理”查看列表）")

        self._refresh_audio_batch_window()

    def _open_audio_batch_window(self):
        if self.audio_batch_window is not None and self.audio_batch_window.winfo_exists():
            self.audio_batch_window.lift()
            self.audio_batch_window.focus()
            return

        self.audio_batch_window = ctk.CTkToplevel(self)
        self.audio_batch_window.title("多文件批量转写")
        self.audio_batch_window.geometry("520x360")
        self.audio_batch_window.minsize(420, 300)
        self.audio_batch_window.configure(fg_color=Theme.BG)
        self.audio_batch_window.transient(self)
        self.audio_batch_window.protocol("WM_DELETE_WINDOW", self._close_audio_batch_window)

        header = ctk.CTkFrame(self.audio_batch_window, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        self.audio_batch_count_label = ctk.CTkLabel(header, text="已选文件: 0",
                                                    font=ctk.CTkFont(size=12, weight="bold"),
                                                    text_color=Theme.TEXT)
        self.audio_batch_count_label.pack(side="left")

        btn_row = ctk.CTkFrame(self.audio_batch_window, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        add_btn = ctk.CTkButton(btn_row, text="添加文件",
                                width=90, height=30,
                                font=ctk.CTkFont(size=12),
                                fg_color=Theme.CARD,
                                hover_color=Theme.CARD_HOVER,
                                border_width=1, border_color=Theme.BORDER,
                                command=lambda: self._pick_audio_files(append=True))
        add_btn.pack(side="left")

        clear_btn = ctk.CTkButton(btn_row, text="清空",
                                  width=70, height=30,
                                  font=ctk.CTkFont(size=12),
                                  fg_color=Theme.CARD,
                                  hover_color=Theme.CARD_HOVER,
                                  border_width=1, border_color=Theme.BORDER,
                                  command=self._clear_audio_files)
        clear_btn.pack(side="left", padx=(10, 0))

        close_btn = ctk.CTkButton(btn_row, text="关闭",
                                  width=70, height=30,
                                  font=ctk.CTkFont(size=12),
                                  fg_color=Theme.CARD,
                                  hover_color=Theme.CARD_HOVER,
                                  border_width=1, border_color=Theme.BORDER,
                                  command=self._close_audio_batch_window)
        close_btn.pack(side="right")

        list_card = ctk.CTkFrame(self.audio_batch_window, fg_color=Theme.CARD, corner_radius=8,
                                 border_width=1, border_color=Theme.BORDER)
        list_card.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.audio_batch_textbox = ctk.CTkTextbox(list_card, font=ctk.CTkFont(size=11),
                                                  fg_color="transparent", text_color=Theme.TEXT_SECONDARY)
        self.audio_batch_textbox.pack(fill="both", expand=True, padx=8, pady=8)
        self.audio_batch_textbox.configure(state="disabled")

        self._refresh_audio_batch_window()

    def _refresh_audio_batch_window(self):
        if self.audio_batch_window is None or not self.audio_batch_window.winfo_exists():
            return
        if self.audio_batch_count_label is not None:
            self.audio_batch_count_label.configure(text=f"已选文件: {len(self.audio_files)}")
        if self.audio_batch_textbox is not None:
            self.audio_batch_textbox.configure(state="normal")
            self.audio_batch_textbox.delete("1.0", "end")
            if self.audio_files:
                self.audio_batch_textbox.insert("1.0", "\n".join(self.audio_files))
            self.audio_batch_textbox.configure(state="disabled")

    def _close_audio_batch_window(self):
        if self.audio_batch_window is not None and self.audio_batch_window.winfo_exists():
            self.audio_batch_window.destroy()
        self.audio_batch_window = None
        self.audio_batch_textbox = None
        self.audio_batch_count_label = None

    def _pick_text_files(self, append: bool = False):
        paths = filedialog.askopenfilenames(filetypes=[("文本文件", "*.txt *.md *.text"), ("所有文件", "*.*")])
        if not paths:
            return
        self._set_text_files(paths, append=append)

    def _set_text_files(self, paths: Sequence[str], append: bool = False):
        if append:
            existing = {os.path.normcase(p) for p in self.text_files}
            for p in paths:
                key = os.path.normcase(p)
                if key not in existing:
                    self.text_files.append(p)
                    existing.add(key)
        else:
            self.text_files = list(paths)
        self._update_text_files_display()

    def _clear_text_files(self):
        self.text_files = []
        self._update_text_files_display()

    def _update_text_files_display(self):
        if not self.text_files:
            self.text_files_label.configure(text="未选择文件")
            self.url_entry.delete(0, "end")
        elif len(self.text_files) == 1:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, self.text_files[0])
            name = self._ellipsize(os.path.basename(self.text_files[0]), max_len=40)
            self.text_files_label.configure(text=f"已选择: {name}")
        else:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, f"已选择 {len(self.text_files)} 个文件")
            self.text_files_label.configure(text=f"已选择 {len(self.text_files)} 个文件（点击“批量管理”查看列表）")
        self._refresh_batch_window()

    def _ellipsize(self, text: str, max_len: int = 40) -> str:
        if len(text) <= max_len:
            return text
        if max_len <= 3:
            return text[:max_len]
        return text[:max_len - 3] + "..."

    def _open_text_batch_window(self):
        if self.batch_window is not None and self.batch_window.winfo_exists():
            self.batch_window.lift()
            self.batch_window.focus()
            return

        self.batch_window = ctk.CTkToplevel(self)
        self.batch_window.title("多文件批量清洗")
        self.batch_window.geometry("520x360")
        self.batch_window.minsize(420, 300)
        self.batch_window.configure(fg_color=Theme.BG)
        self.batch_window.transient(self)
        self.batch_window.protocol("WM_DELETE_WINDOW", self._close_batch_window)

        header = ctk.CTkFrame(self.batch_window, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 8))

        self.batch_count_label = ctk.CTkLabel(header, text="已选文件: 0",
                                              font=ctk.CTkFont(size=12, weight="bold"),
                                              text_color=Theme.TEXT)
        self.batch_count_label.pack(side="left")

        btn_row = ctk.CTkFrame(self.batch_window, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        add_btn = ctk.CTkButton(btn_row, text="添加文件",
                                width=90, height=30,
                                font=ctk.CTkFont(size=12),
                                fg_color=Theme.CARD,
                                hover_color=Theme.CARD_HOVER,
                                border_width=1, border_color=Theme.BORDER,
                                command=lambda: self._pick_text_files(append=True))
        add_btn.pack(side="left")

        clear_btn = ctk.CTkButton(btn_row, text="清空",
                                  width=70, height=30,
                                  font=ctk.CTkFont(size=12),
                                  fg_color=Theme.CARD,
                                  hover_color=Theme.CARD_HOVER,
                                  border_width=1, border_color=Theme.BORDER,
                                  command=self._clear_text_files)
        clear_btn.pack(side="left", padx=(10, 0))

        close_btn = ctk.CTkButton(btn_row, text="关闭",
                                  width=70, height=30,
                                  font=ctk.CTkFont(size=12),
                                  fg_color=Theme.CARD,
                                  hover_color=Theme.CARD_HOVER,
                                  border_width=1, border_color=Theme.BORDER,
                                  command=self._close_batch_window)
        close_btn.pack(side="right")

        list_card = ctk.CTkFrame(self.batch_window, fg_color=Theme.CARD, corner_radius=8,
                                 border_width=1, border_color=Theme.BORDER)
        list_card.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.batch_textbox = ctk.CTkTextbox(list_card, font=ctk.CTkFont(size=11),
                                            fg_color="transparent", text_color=Theme.TEXT_SECONDARY)
        self.batch_textbox.pack(fill="both", expand=True, padx=8, pady=8)
        self.batch_textbox.configure(state="disabled")

        self._refresh_batch_window()

    def _refresh_batch_window(self):
        if self.batch_window is None or not self.batch_window.winfo_exists():
            return
        if self.batch_count_label is not None:
            self.batch_count_label.configure(text=f"已选文件: {len(self.text_files)}")
        if self.batch_textbox is not None:
            self.batch_textbox.configure(state="normal")
            self.batch_textbox.delete("1.0", "end")
            if self.text_files:
                self.batch_textbox.insert("1.0", "\n".join(self.text_files))
            self.batch_textbox.configure(state="disabled")

    def _close_batch_window(self):
        if self.batch_window is not None and self.batch_window.winfo_exists():
            self.batch_window.destroy()
        self.batch_window = None
        self.batch_textbox = None
        self.batch_count_label = None
    
    def _log(self, msg: str):
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")

    def _bind_output_shortcuts(self):
        self.bind_all("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self.bind_all("<Control-Button-4>", lambda _e: self._zoom_output_text(1))
        self.bind_all("<Control-Button-5>", lambda _e: self._zoom_output_text(-1))
        self.bind_all("<Control-plus>", lambda _e: self._zoom_output_text(1))
        self.bind_all("<Control-equal>", lambda _e: self._zoom_output_text(1))
        self.bind_all("<Control-minus>", lambda _e: self._zoom_output_text(-1))
        self.bind_all("<Control-0>", self._reset_output_zoom)

    def _on_ctrl_mousewheel(self, event):
        if event.delta == 0:
            return "break"
        return self._zoom_output_text(1 if event.delta > 0 else -1)

    def _zoom_output_text(self, delta: int):
        next_log_size = max(self.min_output_font_size, min(self.max_output_font_size, self.log_font_size + delta))
        next_result_size = max(self.min_output_font_size, min(self.max_output_font_size, self.result_font_size + delta))
        if next_log_size == self.log_font_size and next_result_size == self.result_font_size:
            return "break"
        self.log_font_size = next_log_size
        self.result_font_size = next_result_size
        self.log_font.configure(size=self.log_font_size)
        self.result_font.configure(size=self.result_font_size)
        return "break"

    def _reset_output_zoom(self, _event=None):
        self.log_font_size = 11
        self.result_font_size = 12
        self.log_font.configure(size=self.log_font_size)
        self.result_font.configure(size=self.result_font_size)
        return "break"
    
    def _update_progress(self, step: int, total: int, msg: str):
        pct = step / total
        self.progress_bar.set(pct)
        self.progress_pct.configure(text=f"{int(pct*100)}%")
        self.status_label.configure(text=msg)
        self._log(msg)
    
    def _start_processing(self):
        input_val = self.url_entry.get().strip()
        text_val = None
        
        # 如果是文本清洗模式，检查文本输入框
        if self.current_mode == "text":
            text_val = self.text_input.get("1.0", "end").strip()
            if not input_val and not text_val and not self.text_files:
                messagebox.showwarning("提示", "请选择文件或输入文本内容")
                return
        else:
            if self.current_mode == "audio":
                if not self.audio_files and not input_val:
                    messagebox.showwarning("提示", "请选择音频文件")
                    return
            elif not input_val:
                messagebox.showwarning("提示", "请输入内容")
                return
        
        if self.is_processing:
            return
        self.is_processing = True
        self.start_btn.configure(state="disabled", text="处理中...")
        self.log_text.delete("1.0", "end")
        self.result_text.delete("1.0", "end")
        self.copy_btn.configure(state="disabled")
        self.save_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_pct.configure(text="", text_color=Theme.ACCENT)
        self.status_label.configure(text="处理中...")
        thread = threading.Thread(target=self._process, args=(input_val, text_val), daemon=True)
        thread.start()
    
    def _process(self, input_val: str, text_val: Optional[str] = None):
        try:
            import traceback
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if self.current_mode == "text":
                from text_cleaner import TextCleaner
                self.after(0, lambda: self._log("初始化文本清洗工具..."))
                cleaner = TextCleaner()
                def cb_text(s, t): self.after(0, lambda: self._update_progress(s, t, f"清洗中: {s}/{t}"))
                
                # 如果有直接输入的文本，使用文本清洗；否则使用文件清洗
                if text_val:
                    self.after(0, lambda: self._log("清洗直接输入的文本..."))
                    md = loop.run_until_complete(cleaner.clean_text(text_val, progress_callback=cb_text))
                    out = "直接输入文本"
                    self.after(0, lambda: self._on_done(out, md))
                elif self.text_files:
                    results = []
                    total = len(self.text_files)
                    for i, file_path in enumerate(self.text_files, start=1):
                        self.after(0, lambda i=i, t=total, p=file_path: self._log(f"批量处理 {i}/{t}: {os.path.basename(p)}"))
                        try:
                            out = loop.run_until_complete(cleaner.clean_file(file_path, progress_callback=cb_text))
                            results.append({'file': file_path, 'output': out, 'success': True})
                        except Exception as e:
                            err_msg = f"{type(e).__name__}: {str(e)}"
                            self.after(0, lambda p=file_path, m=err_msg: self._log(f"失败: {os.path.basename(p)} - {m}"))
                            results.append({'file': file_path, 'error': err_msg, 'success': False})
                    self.after(0, lambda: self._on_batch_done(results))
                else:
                    out = loop.run_until_complete(cleaner.clean_file(input_val, progress_callback=cb_text))
                    with open(out, 'r', encoding='utf-8') as f:
                        md = f.read()
                    self.after(0, lambda: self._on_done(out, md))
            else:
                from main import VideoToMarkdown
                if self.pipeline is None:
                    self.after(0, lambda: self._log("初始化Pipeline..."))
                    self.pipeline = VideoToMarkdown()
                def cb_pipe(s, t, m): self.after(0, lambda: self._update_progress(s, t, m))
                if self.current_mode == "url":
                    out, md = loop.run_until_complete(self.pipeline.process_url(input_val, cb_pipe))
                    self.after(0, lambda: self._on_done(out, md))
                elif self.current_mode == "audio":
                    if self.audio_files and len(self.audio_files) > 1:
                        results = []
                        total = len(self.audio_files)
                        for i, audio_path in enumerate(self.audio_files, start=1):
                            self.after(0, lambda i=i, t=total, p=audio_path: self._log(f"批量处理 {i}/{t}: {os.path.basename(p)}"))
                            try:
                                out, _md = loop.run_until_complete(self.pipeline.process_audio(audio_path, cb_pipe))
                                results.append({'file': audio_path, 'output': out, 'success': True})
                            except Exception as e:
                                err_msg = f"{type(e).__name__}: {str(e)}"
                                self.after(0, lambda p=audio_path, m=err_msg: self._log(f"失败: {os.path.basename(p)} - {m}"))
                                results.append({'file': audio_path, 'error': err_msg, 'success': False})
                        self.after(0, lambda: self._on_batch_done(results))
                    else:
                        audio_path = self.audio_files[0] if self.audio_files else input_val
                        out, md = loop.run_until_complete(self.pipeline.process_audio(audio_path, cb_pipe))
                        self.after(0, lambda: self._on_done(out, md))
                else:
                    results = loop.run_until_complete(self.pipeline.process_audio_folder(input_val, cb_pipe))
                    self.after(0, lambda: self._on_batch_done(results))
            loop.close()
        except Exception as e:
            import traceback
            err_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            self.after(0, lambda msg=err_msg: self._on_error(msg))
    
    def _on_done(self, path: str, md: str):
        self.is_processing = False
        self.start_btn.configure(state="normal", text="▶  一键处理")
        self.status_label.configure(text=f"完成: {path}")
        self.progress_pct.configure(text="100%", text_color=Theme.SUCCESS)
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", md)
        self.copy_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        self._log(f"完成: {path}")
        self.tabview.set("结果")
    
    def _on_batch_done(self, results: list):
        self.is_processing = False
        self.start_btn.configure(state="normal", text="▶  一键处理")
        ok = sum(1 for r in results if r['success'])
        self.status_label.configure(text=f"完成: {ok}/{len(results)}")
        self.progress_pct.configure(text="100%", text_color=Theme.SUCCESS)
        summary = "\n".join(
            f"{'OK' if r['success'] else 'FAIL'}: {os.path.basename(r['file'])}"
            + (f" - {r['error']}" if not r['success'] and r.get('error') else "")
            for r in results
        )
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", summary)
        self.copy_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        self.tabview.set("结果")
    
    def _on_error(self, err: str):
        self.is_processing = False
        self.start_btn.configure(state="normal", text="▶  一键处理")
        lines = [line.strip() for line in err.splitlines() if line.strip()]
        short_err = lines[0] if lines else "处理失败"
        short_err = self._ellipsize(short_err, max_len=120)
        self.status_label.configure(text=f"错误: {short_err}")
        self.progress_pct.configure(text="!", text_color=Theme.ERROR)
        self._log(f"错误: {err}")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", err)
        self.copy_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        self.tabview.set("结果")
        messagebox.showerror("错误", short_err)
    
    def _copy_result(self):
        txt = self.result_text.get("1.0", "end").strip()
        if txt:
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.status_label.configure(text="已复制")
    
    def _save_result(self):
        txt = self.result_text.get("1.0", "end").strip()
        if not txt:
            return
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Text", "*.txt")])
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(txt)
            self.status_label.configure(text=f"已保存: {path}")


def main():
    app = ProVideoToMarkdownGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
