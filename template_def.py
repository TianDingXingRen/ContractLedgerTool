"""模板定义管理模块

.contract-template 格式的加载、保存、验证、列表管理
"""

import json
import os
import re
import shutil
import time
import logging
from datetime import datetime

from utils.security import path_within as _path_within
from utils.constants import FieldType

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')


def _ensure_dir():
    os.makedirs(TEMPLATES_DIR, exist_ok=True)


class TemplateValidationError(Exception):
    pass


class TemplateDef:
    """模板定义封装"""

    REQUIRED_FIELDS = {'format_version', 'template_name', 'source_docx', 'fields'}
    VALID_FIELD_TYPES = {ft.value for ft in FieldType}
    VALID_LOCATION_TYPES = {'paragraph', 'table', 'table_cell'}

    def __init__(self, data=None):
        self.data = data or self._default()
        self._path = None

    @staticmethod
    def _default():
        return {
            'format_version': '1.0',
            'template_name': '',
            'source_docx': '',
            'fields': [],
        }

    @classmethod
    def create(cls, name, source_docx, fields):
        """从检测结果创建模板定义"""
        data = cls._default()
        data['template_name'] = name
        data['source_docx'] = source_docx
        data['fields'] = fields
        return cls(data)

    @classmethod
    def load(cls, path):
        """从文件加载模板定义"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 确保所有字段都有 id（兼容手动创建/旧版模板）
        for i, field in enumerate(data.get('fields', [])):
            if 'id' not in field:
                field['id'] = i
        obj = cls(data)
        obj._path = path
        return obj

    def save(self, path=None):
        """保存模板定义到文件（自动备份旧版本）"""
        _ensure_dir()
        self._path = path or self._path or self._default_path()
        _backup_before_save(self._path)
        tmp = self._path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)
        return self._path

    def _default_path(self):
        name = re.sub(r'[^\w\u4e00-\u9fff]', '_', self.data.get('template_name', 'untitled'))
        return os.path.join(TEMPLATES_DIR, f'{name}.contract-template')

    def validate(self):
        """验证模板定义完整性"""
        errors = []
        for field in self.REQUIRED_FIELDS:
            if field not in self.data:
                errors.append(f'缺少必需字段: {field}')

        if not isinstance(self.data.get('fields'), list):
            errors.append('fields 必须是数组')
        else:
            seen_keys = set()
            for i, f in enumerate(self.data['fields']):
                key = f.get('key')
                if not key:
                    errors.append(f'fields[{i}] 缺少 key')
                elif key in seen_keys:
                    errors.append(f'fields[{i}] 字段 key 重复: {key}')
                else:
                    seen_keys.add(key)
                if not f.get('label'):
                    errors.append(f'fields[{i}] 缺少 label')
                if f.get('field_type') not in self.VALID_FIELD_TYPES:
                    errors.append(f'fields[{i}] 无效的 field_type: {f.get("field_type")}')
                if f.get('field_type') == 'select' and not f.get('options'):
                    errors.append(f'fields[{i}] select 类型缺少 options')
                if f.get('field_type') == 'number':
                    min_value = f.get('min_value')
                    max_value = f.get('max_value')
                    if min_value is not None and max_value is not None and min_value > max_value:
                        errors.append(f'fields[{i}] number 类型最小值不能大于最大值')
                if f.get('field_type') == 'calculated':
                    if not f.get('formula'):
                        errors.append(f'fields[{i}] calculated 类型缺少 formula')
                if f.get('field_type') == 'table':
                    if not f.get('columns'):
                        errors.append(f'fields[{i}] table 类型缺少 columns')
                    else:
                        col_keys = set()
                        for ci, col in enumerate(f.get('columns', [])):
                            col_key = col.get('key')
                            if not col_key:
                                errors.append(f'fields[{i}].columns[{ci}] 缺少 key')
                            elif col_key in col_keys:
                                errors.append(f'fields[{i}].columns[{ci}] 列 key 重复: {col_key}')
                            else:
                                col_keys.add(col_key)
                            if not col.get('label'):
                                errors.append(f'fields[{i}].columns[{ci}] 缺少 label')
                            if col.get('field_type') not in {'text', 'number', 'textarea', 'select', 'calculated'}:
                                errors.append(f'fields[{i}].columns[{ci}] 字段类型无效')
                            if col.get('field_type') == 'select' and not col.get('options'):
                                errors.append(f'fields[{i}].columns[{ci}] select 类型缺少 options')
                            if col.get('field_type') == 'calculated' and not col.get('formula'):
                                errors.append(f'fields[{i}].columns[{ci}] calculated 类型缺少 formula')
                loc = f.get('location', {})
                loc_type = loc.get('type')
                if loc_type not in self.VALID_LOCATION_TYPES:
                    errors.append(f'fields[{i}] 无效的 location.type: {loc.get("type")}')
                else:
                    # 校验各 location 类型的必需字段
                    if loc_type == 'paragraph':
                        body_index = loc.get('body_index')
                        if not isinstance(body_index, int):
                            errors.append(f'fields[{i}] paragraph 类型缺少有效的 body_index')
                    elif loc_type == 'table':
                        table_index = loc.get('table_index')
                        if not isinstance(table_index, int):
                            errors.append(f'fields[{i}] table 类型缺少有效的 table_index')
                        template_row_index = loc.get('template_row_index')
                        if not isinstance(template_row_index, int):
                            errors.append(f'fields[{i}] table 类型缺少有效的 template_row_index')
                    elif loc_type == 'table_cell':
                        for key in ('table_index', 'row_index', 'col_index'):
                            if not isinstance(loc.get(key), int):
                                errors.append(f'fields[{i}] table_cell 类型缺少有效的 {key}')

        if not errors:
            try:
                import field_eval
                field_eval.sort_fields_by_dependency(self.data['fields'])
            except Exception as e:
                errors.append(f'计算字段依赖无效: {e}')

        if errors:
            raise TemplateValidationError('; '.join(errors))

    def to_dict(self):
        """转为字典"""
        return self.data

    @property
    def name(self):
        return self.data.get('template_name', '未命名模板')

    @property
    def field_count(self):
        return len(self.data.get('fields', []))

    def get_field_by_key(self, key):
        for f in self.data.get('fields', []):
            if f.get('key') == key:
                return f
        return None


def list_templates():
    """列出所有已保存的模板"""
    _ensure_dir()
    templates = []
    if not os.path.isdir(TEMPLATES_DIR):
        return templates

    for fname in os.listdir(TEMPLATES_DIR):
        if not fname.endswith('.contract-template'):
            continue
        path = os.path.join(TEMPLATES_DIR, fname)
        try:
            tpl = TemplateDef.load(path)
            stat = os.stat(path)
            templates.append({
                'path': path,
                'name': tpl.name,
                'filename': fname,
                'field_count': tpl.field_count,
                'category': tpl.data.get('category', ''),
                'created': time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_ctime)),
                'modified': time.strftime('%Y-%m-%d %H:%M', time.localtime(stat.st_mtime)),
            })
        except Exception:
            logging.getLogger('contract_tool').warning(
                '模板文件 %s 加载失败，将使用部分信息展示', fname, exc_info=True)
            templates.append({
                'path': path,
                'name': fname.replace('.contract-template', ''),
                'filename': fname,
                'field_count': 0,
                'category': '',
                'created': '',
                'modified': '',
            })

    templates.sort(key=lambda t: t['modified'], reverse=True)
    return templates


def delete_template(filename):
    """删除模板文件"""
    _ensure_dir()
    filename = os.path.basename(filename or '')
    if not filename.endswith('.contract-template'):
        return False
    templates_root = os.path.realpath(TEMPLATES_DIR)
    path = os.path.realpath(os.path.join(TEMPLATES_DIR, filename))
    if os.path.commonpath([templates_root, path]) != templates_root:
        return False
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def copy_template(filename):
    """复制模板（创建副本）"""
    _ensure_dir()
    filename = os.path.basename(filename or '')
    if not filename.endswith('.contract-template'):
        return False
    templates_root = os.path.realpath(TEMPLATES_DIR)
    path = os.path.realpath(os.path.join(TEMPLATES_DIR, filename))
    if os.path.commonpath([templates_root, path]) != templates_root:
        return False
    if not os.path.exists(path):
        return False
    try:
        tpl = TemplateDef.load(path)
    except Exception:
        return False
    # 修改模板名称
    original_name = tpl.data.get('template_name', '未命名模板')
    new_name = original_name + ' (副本)'
    # 确保不重名
    existing = list_templates()
    existing_names = {e['name'] for e in existing}
    counter = 1
    base_name = new_name
    MAX_NAME_RETRIES = 1000
    while new_name in existing_names:
        counter += 1
        if counter > MAX_NAME_RETRIES:
            raise RuntimeError('无法生成唯一模板名称')
        new_name = f'{base_name} {counter}'
    tpl.data['template_name'] = new_name
    # 保存为新文件
    new_filename = re.sub(r'[^\w一-鿿]', '_', new_name) + '.contract-template'
    new_path = os.path.join(TEMPLATES_DIR, new_filename)
    # 如果文件名冲突（尽管名称不同但文件名相同），加后缀
    file_counter = 1
    MAX_FILE_RETRIES = 1000
    while os.path.exists(new_path):
        file_counter += 1
        if file_counter > MAX_FILE_RETRIES:
            raise RuntimeError('无法生成唯一文件名')
        new_filename = re.sub(r'[^\w一-鿿]', '_', new_name) + f'_{file_counter}.contract-template'
        new_path = os.path.join(TEMPLATES_DIR, new_filename)
    tpl.save(new_path)
    return os.path.basename(new_path)


VERSIONS_DIR = 'versions'


def _safe_template_stem(template_name):
    safe = re.sub(r'[^\w\u4e00-\u9fff.-]', '_', str(template_name or ''))
    safe = safe.strip(' .')
    if not safe or safe in {'.', '..'}:
        raise ValueError('模板名称无效')
    return safe


def _versions_dir(template_name):
    safe = _safe_template_stem(template_name)
    return os.path.join(TEMPLATES_DIR, VERSIONS_DIR, safe)


_MAX_VERSIONS_PER_TEMPLATE = 50  # 每个模板最多保留的历史版本数

def _backup_before_save(path):
    """如果文件已存在且有内容，备份到版本目录，超出上限时清理旧版本"""
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        name = os.path.basename(path).replace('.contract-template', '')
        vdir = _versions_dir(name)
        os.makedirs(vdir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        backup = os.path.join(vdir, f'{ts}.contract-template')
        with open(backup, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 清理超出上限的旧版本（按文件名降序，最旧的在前）
        existing = sorted(
            [f for f in os.listdir(vdir) if f.endswith('.contract-template')],
            reverse=True,
        )
        for old_file in existing[_MAX_VERSIONS_PER_TEMPLATE:]:
            try:
                os.remove(os.path.join(vdir, old_file))
            except OSError:
                logging.getLogger('contract_tool').warning(
                    '无法清理超出保留上限的模板版本: %s', old_file, exc_info=True,
                )
    except Exception:
        logging.getLogger('contract_tool').warning(
            '保存前版本备份失败: %s', path, exc_info=True)


def list_versions(template_name):
    """列出模板的所有历史版本"""
    try:
        vdir = _versions_dir(template_name)
    except ValueError:
        return []
    if not os.path.isdir(vdir):
        return []
    versions = []
    for fname in os.listdir(vdir):
        if not fname.endswith('.contract-template'):
            continue
        fpath = os.path.join(vdir, fname)
        stat = os.stat(fpath)
        ts_str = fname.replace('.contract-template', '')
        try:
            try:
                ts = datetime.strptime(ts_str, '%Y%m%d_%H%M%S_%f')
            except ValueError:
                ts = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
            display = ts.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            display = ts_str
        versions.append({
            'filename': fname,
            'display': display,
            'size': stat.st_size,
        })
    versions.sort(key=lambda v: v['filename'], reverse=True)
    return versions


def restore_version(template_name, version_filename):
    """恢复某个历史版本（当前版本也会被备份）"""
    vdir = _versions_dir(template_name)
    version_filename = os.path.basename(version_filename or '')
    if not version_filename.endswith('.contract-template'):
        raise FileNotFoundError(f'版本文件不存在: {version_filename}')
    src = os.path.abspath(os.path.join(vdir, version_filename))
    if not _path_within(vdir, src) or not os.path.exists(src):
        raise FileNotFoundError(f'版本文件不存在: {version_filename}')
    safe_name = _safe_template_stem(template_name)
    main_path = os.path.abspath(os.path.join(TEMPLATES_DIR, f'{safe_name}.contract-template'))
    if not _path_within(TEMPLATES_DIR, main_path):
        raise FileNotFoundError(f'模板文件不存在: {template_name}')
    if os.path.exists(main_path):
        before_restore = os.path.join(vdir,
            datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_before_restore.contract-template')
        try:
            shutil.copy2(main_path, before_restore)
        except Exception:
            logging.getLogger('contract_tool').warning(
                '版本回滚前备份当前模板失败: %s', template_name, exc_info=True)
    with open(src, 'r', encoding='utf-8') as f:
        json.load(f)
    shutil.copy2(src, main_path)
    return main_path
