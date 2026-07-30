"""Contract document download and on-demand PDF export routes."""

from __future__ import annotations

import os

from flask import request, send_file

import ledger_store
import pdf_exporter
from runtime.flask_paths import current_runtime_paths
from services.contract_output_service import generated_pdf_path
from utils.errors import GENERIC_ERROR
from utils.field_utils import safe_filename_part
from utils.logger import get_logger
from utils.security import path_within


def _contract_file_context(contract_id):
    contract = ledger_store.get_contract(contract_id)
    if not contract:
        return None, ('合同记录不存在', 404)
    docx_path = contract.get('docx_path') or ''
    output_dir = str(current_runtime_paths().output_dir)
    if (
        not docx_path
        or not path_within(output_dir, docx_path)
        or not os.path.exists(docx_path)
    ):
        return None, ('合同文件不存在，可能已被移动或删除', 404)
    return (contract, docx_path, output_dir), None


def _convert_pdf(contract_id, docx_path, pdf_path):
    try:
        pdf_exporter.convert_docx_to_pdf(docx_path, pdf_path)
    except FileNotFoundError as exc:
        get_logger().warning(
            'PDF 导出失败-文件未找到 (contract %d): %s', contract_id, exc
        )
        return (
            'PDF 导出失败。提示：安装 LibreOffice（免费）即可导出 PDF。'
            '\n下载地址：https://www.libreoffice.org',
            400,
        )
    except RuntimeError as exc:
        get_logger().warning(
            'PDF 导出失败 (contract %d): %s', contract_id, exc
        )
        return (
            'PDF 导出失败。\n\n提示：安装 LibreOffice（免费）即可导出 PDF。'
            '\n下载地址：https://www.libreoffice.org',
            400,
        )
    except Exception as exc:
        get_logger().error(
            'PDF 导出异常 (contract %d): %s',
            contract_id,
            exc,
            exc_info=True,
        )
        return GENERIC_ERROR, 500
    return None


def register_contract_download_routes(bp):
    @bp.route('/contracts/<int:contract_id>/download')
    def contract_download(contract_id):
        context, error = _contract_file_context(contract_id)
        if error:
            return error
        contract, docx_path, _output_dir = context
        base = contract.get('contract_no') or f'contract_{contract_id}'
        return send_file(
            docx_path,
            as_attachment=True,
            download_name=f'{base}.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    @bp.route('/contracts/<int:contract_id>/download-pdf', methods=['GET', 'POST'])
    def contract_download_pdf(contract_id):
        context, error = _contract_file_context(contract_id)
        if error:
            return error
        contract, docx_path, output_dir = context
        base = contract.get('contract_no') or f'contract_{contract_id}'
        safe_base = safe_filename_part(base, f'contract_{contract_id}')
        pdf_path = generated_pdf_path(docx_path)
        if not path_within(output_dir, pdf_path):
            return 'PDF 输出路径无效', 400
        if request.method == 'POST':
            conversion_error = _convert_pdf(contract_id, docx_path, pdf_path)
            if conversion_error:
                return conversion_error
        elif not os.path.isfile(pdf_path):
            return 'PDF 文件尚未生成', 404
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'{safe_base}.pdf',
            mimetype='application/pdf',
        )
