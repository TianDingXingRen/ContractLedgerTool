#!/usr/bin/env python3
"""Generate unified icons.js with consistent visual style."""
import re, os

icons_js_content = r'''/**
 * icons.js - 统一风格界面图标集
 *
 * 设计规范:
 *   - 24x24 viewBox, 留1px安全边距
 *   - 描边宽度 1.75px, 视觉密度统一
 *   - 圆角端点/圆角连接 (round cap/join)
 *   - 矩形元素 rx=1.5
 *   - 纯描边风格为主, 少量填充点缀
 *
 * 用法: <i data-lucide="icon-name" class="w-4 h-4"></i>
 */
(function() {
  'use strict';

  var W = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">';

  var I = {
    // ==== Navigation & System ====
    "layout-grid":  '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "menu":         '<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>',
    "chevron-right":'<path d="m8 5 7 7-7 7"/>',
    "power":        '<path d="M18.5 6.5A8.5 8.5 0 1 1 5.5 6.5"/><line x1="12" y1="3" x2="12" y2="11"/>',

    // ==== Contract & Document ====
    "pen-line":     '<path d="M16 3l5 5L8 21H3v-5L16 3z"/><line x1="12" y1="20" x2="20" y2="20"/>',
    "file-text":    '<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v6h6"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/>',
    "file-spreadsheet":'<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v6h6"/><line x1="8" y1="12" x2="10" y2="12"/><line x1="13" y1="12" x2="15" y2="12"/><line x1="8" y1="16" x2="10" y2="16"/><line x1="13" y1="16" x2="15" y2="16"/>',
    "file-down":    '<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v6h6"/><path d="m9 14 3 3 3-3"/><line x1="12" y1="17" x2="12" y2="11"/>',
    "file-up":      '<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v6h6"/><path d="m9 15 3-3 3 3"/><line x1="12" y1="18" x2="12" y2="12"/>',
    "copy":         '<rect x="8" y="8" width="12" height="13" rx="1.5"/><path d="M4 16V5a1.5 1.5 0 0 1 1.5-1.5H16"/>',

    // ==== Ledger & Data ====
    "book-open":    '<path d="M4 4h5a3 3 0 0 1 3 3v11a2.5 2.5 0 0 0-2.5-2.5H4z"/><path d="M20 4h-5a3 3 0 0 0-3 3v11a2.5 2.5 0 0 1 2.5-2.5H20z"/><line x1="12" y1="9" x2="12" y2="16"/>',
    "database":     '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.5 3.6 3 8 3s8-1.5 8-3V5"/><path d="M4 11v6c0 1.5 3.6 3 8 3s8-1.5 8-3v-6"/>',
    "database-backup":'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.5 3.6 3 8 3s8-1.5 8-3V5"/><path d="M4 12c0 1.5 3.6 3 8 3s8-1.5 8-3"/>',
    "history":      '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/><path d="M3.5 4.5v3.5h3.5"/>',

    // ==== Procurement & Business ====
    "briefcase-business":'<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="9.5" y1="14" x2="14.5" y2="14"/>',
    "chart-no-axes-combined":'<line x1="4" y1="20" x2="20" y2="20"/><rect x="5" y="12" width="3" height="8" rx="0.75"/><rect x="10.5" y="7" width="3" height="13" rx="0.75"/><rect x="16" y="4" width="3" height="16" rx="0.75"/>',
    "milestone":    '<path d="M12 2v20"/><path d="M18 6 12 12 6 6"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/>',
    "folder-tree":  '<path d="M3 6v12a1 1 0 0 0 1 1h6l2-2h8a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H9L7 4H4a1 1 0 0 0-1 1z" fill="currentColor" fill-opacity="0.12" stroke="currentColor"/><path d="M9 11h9"/><path d="M9 15h6"/>',
    "folder-open":  '<path d="M3 7v10a1 1 0 0 0 1 1h12l3-7H7L4 17" fill="currentColor" fill-opacity="0.12" stroke="currentColor"/><path d="M7 7V5a1 1 0 0 1 1-1h4l2 2h5a1 1 0 0 1 1 1v4"/>',
    "banknote":     '<rect x="2" y="6" width="20" height="12" rx="1.5"/><circle cx="12" cy="12" r="2.5"/><path d="M6.5 12h.5M17 12h.5"/>',

    // ==== Date & Time ====
    "calendar":     '<rect x="3" y="5" width="18" height="17" rx="1.5"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/>',
    "calendar-days":'<rect x="3" y="5" width="18" height="17" rx="1.5"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><rect x="7" y="13" width="4" height="3" rx="0.5"/><rect x="13" y="13" width="4" height="3" rx="0.5"/><rect x="7" y="17" width="4" height="3" rx="0.5"/><rect x="13" y="17" width="4" height="3" rx="0.5"/>',
    "clock":        '<circle cx="12" cy="12" r="9"/><polyline points="12 6.5 12 12 15.5 14"/>',

    // ==== Actions & Operations ====
    "plus":         '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "x":            '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    "check":        '<polyline points="5 12 10 17 19 8"/>',
    "save":         '<path d="M5 21h14a1 1 0 0 0 1-1V6l-4-4H6a1 1 0 0 0-1 1v17"/><path d="M7 2v6h10V2"/><line x1="7" y1="17" x2="17" y2="17"/><line x1="7" y1="13" x2="15" y2="13"/>',
    "download":     '<path d="M5 20h14"/><path d="M12 3v13"/><polyline points="8 12 12 16 16 12"/>',
    "upload":       '<path d="M5 20h14"/><path d="M12 15V2"/><polyline points="8 6 12 2 16 6"/>',
    "refresh-cw":   '<path d="M3 12a9 9 0 0 1 15.36-6.36L20 7"/><path d="M21 12a9 9 0 0 1-15.36 6.36L4 17"/><polyline points="20 3 20 7 16 7"/><polyline points="4 21 4 17 8 17"/>',
    "rotate-ccw":   '<path d="M3 12a9 9 0 0 0 15.36 6.36L20 17"/><path d="M21 12a9 9 0 0 0-15.36-6.36L4 7"/><polyline points="20 21 20 17 16 17"/><polyline points="4 3 4 7 8 7"/>',
    "trash-2":      '<path d="M5 6h14"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M7 6v14a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6"/><line x1="10" y1="10" x2="10" y2="16"/><line x1="14" y1="10" x2="14" y2="16"/>',
    "eye":          '<path d="M2 12s3.5-7.5 10-7.5 10 7.5 10 7.5-3.5 7.5-10 7.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',

    // ==== Status & Feedback ====
    "alert-circle": '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="15.5" r="0.8" fill="currentColor" stroke="none"/>',
    "alert-triangle":'<path d="M12 3 2 21h20L12 3z"/><line x1="12" y1="10" x2="12" y2="15"/><circle cx="12" cy="18" r="0.8" fill="currentColor" stroke="none"/>',
    "info":         '<circle cx="12" cy="12" r="9"/><line x1="12" y1="15.5" x2="12" y2="11"/><circle cx="12" cy="8.5" r="0.8" fill="currentColor" stroke="none"/>',
    "activity":     '<path d="M3 12h3l3-8 6 16 3-8h3"/>',
    "inbox":        '<polyline points="21 13 16 13 14 16 10 16 8 13 3 13"/><path d="M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7"/><path d="M5.5 4.5 3 13v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5l-2.5-8.5"/>',
    "arrow-left-right":'<path d="M8 4 4 8l4 4"/><path d="M16 20l4-4-4-4"/><line x1="4" y1="8" x2="20" y2="8"/><line x1="20" y1="16" x2="4" y2="16"/>',

    // ==== Theme ====
    "sun":          '<circle cx="12" cy="12" r="4.5"/><line x1="12" y1="2" x2="12" y2="4.5"/><line x1="12" y1="19.5" x2="12" y2="22"/><line x1="2" y1="12" x2="4.5" y2="12"/><line x1="19.5" y1="12" x2="22" y2="12"/><line x1="5" y1="5" x2="6.8" y2="6.8"/><line x1="17.2" y1="17.2" x2="19" y2="19"/><line x1="5" y1="19" x2="6.8" y2="17.2"/><line x1="17.2" y1="6.8" x2="19" y2="5"/>',
    "moon":         '
