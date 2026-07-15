"""Excel 单据生成蓝图 — 请购单/单据 Excel 导出功能"""

import json
import os

from flask import render_template, request, jsonify, send_file

import excel_bill_service
from utils import helpers
from utils.logger import get_logger
from utils.errors import GENERIC_ERROR, GENERIC_PARSE_ERROR


def register(app):
    """在 Flask app 上注册 Excel 单据相关路由"""

    @app.route("/excel-bill")
    def excel_bill_page():
        """Excel 单据生成页面"""
        presets = excel_bill_service.get_presets()
        return render_template(
            "excel_bill.html",
            presets=presets,
        )

    @app.route("/api/excel-bill/presets")
    def api_presets():
        """获取所有预置表头列表"""
        presets = excel_bill_service.get_presets()
        return jsonify({"presets": presets})

    @app.route("/api/excel-bill/presets/<preset_key>")
    def api_preset_detail(preset_key):
        """获取某个预置的完整定义（含列信息）"""
        try:
            preset = excel_bill_service.get_preset(preset_key)
            return jsonify(preset)
        except ValueError as e:
            get_logger().error('Excel单据错误: %s', e, exc_info=True)
            return jsonify({"error": GENERIC_ERROR}), 404

    @app.route("/api/excel-bill/contracts")
    def api_contracts_for_bill():
        """获取可用于关联的合同列表"""
        contracts = excel_bill_service.get_contracts_for_selection()
        return jsonify({"contracts": contracts})

    @app.route("/api/excel-bill/contracts/<int:contract_id>/items")
    def api_contract_items(contract_id):
        """获取指定合同的采购标的明细"""
        detail = excel_bill_service.extract_contract_table(contract_id)
        items = detail['rows']
        return jsonify({
            "contract_id": contract_id,
            "table_key": detail['table_key'],
            "item_count": len(items),
            "items": items,
            "columns": detail['columns'],
        })

    # ── 表头数据保存/加载 ──

    @app.route("/api/excel-bill/defaults", methods=["GET"])
    def api_bill_defaults():
        """列出已保存的表头默认值（可按 preset_key 筛选）"""
        preset_key = request.args.get("preset_key", "")
        items = excel_bill_service.list_header_defaults(preset_key or None)
        return jsonify({"defaults": items})

    @app.route("/api/excel-bill/defaults", methods=["POST"])
    def api_save_bill_defaults():
        """保存当前表头填写值"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "请求体为空"}), 400

            preset_key = data.get("preset_key", "standard_pr")
            preset_key = os.path.basename(str(preset_key)) if preset_key else "standard_pr"
            name = data.get("name", "").strip()
            if not name:
                return jsonify({"error": "请输入保存名称"}), 400

            header_data = data.get("header_data", {})
            detail_defaults = data.get("detail_defaults", {})
            column_mapping = data.get("column_mapping", {})

            filename = excel_bill_service.save_header_default(
                preset_key, name, header_data, detail_defaults, column_mapping
            )
            get_logger().info("Bill defaults saved: %s", filename)
            return jsonify({"success": True, "filename": filename, "message": "保存成功"})
        except Exception as e:
            get_logger().error("Save bill defaults failed: %s", e, exc_info=True)
            return jsonify({"error": GENERIC_ERROR}), 500

    @app.route("/api/excel-bill/defaults/<filename>", methods=["GET"])
    def api_load_bill_defaults(filename):
        """加载指定保存的表头默认值"""
        try:
            record = excel_bill_service.load_header_default(filename)
            return jsonify(record)
        except (ValueError, FileNotFoundError) as e:
            get_logger().error('Excel单据错误: %s', e, exc_info=True)
            return jsonify({"error": GENERIC_ERROR}), 404

    @app.route("/api/excel-bill/defaults/<filename>", methods=["DELETE"])
    def api_delete_bill_defaults(filename):
        """删除指定保存的表头默认值"""
        try:
            ok = excel_bill_service.delete_header_default(filename)
            if ok:
                return jsonify({"success": True, "message": "已删除"})
            return jsonify({"error": "删除失败"}), 400
        except Exception as e:
            get_logger().error('Excel单据API错误: %s', e, exc_info=True)
            return jsonify({"error": GENERIC_ERROR}), 500

    @app.route("/excel-bill/generate", methods=["POST"])
    def excel_bill_generate():
        """生成 Excel 单据文件并下载"""
        try:
            preset_key = request.form.get("preset_key", "standard_pr")
            bill_no = request.form.get("bill_no", "").strip()

            # 解析表头数据
            header_json = request.form.get("header_data", "{}")
            try:
                header_data = json.loads(header_json)
            except (json.JSONDecodeError, TypeError):
                header_data = {}
            if bill_no:
                header_data["bill_no"] = bill_no

            # 解析明细数据
            detail_json = request.form.get("detail_data", "[]")
            try:
                detail_rows = json.loads(detail_json)
            except (json.JSONDecodeError, TypeError):
                detail_rows = []

            # 如果指定了合同关联 + 列映射，自动从合同提取明细
            contract_id_str = request.form.get("contract_id", "").strip()
            column_mapping_json = request.form.get("column_mapping", "{}")
            if contract_id_str:
                try:
                    contract_id = int(contract_id_str)
                    column_mapping = json.loads(column_mapping_json)
                    contract_items = excel_bill_service.extract_table_from_contract(contract_id)
                    if contract_items:
                        # 从表单获取默认值
                        default_vals = {}
                        for key in ["buyer", "required_date", "suggested_order_date"]:
                            val = request.form.get("default_" + key, "").strip()
                            if val:
                                default_vals[key] = val
                        mapped_rows = excel_bill_service.map_contract_items_to_detail(
                            contract_items, column_mapping, bill_no, default_vals
                        )
                        detail_rows = mapped_rows
                except (ValueError, json.JSONDecodeError) as e:
                    get_logger().error('合同数据解析失败: %s', e, exc_info=True)
                    return jsonify({"error": GENERIC_PARSE_ERROR}), 400

            # 生成 Excel
            output_dir = os.path.join(helpers.OUTPUT_FOLDER, "excel_bills")
            path = excel_bill_service.generate_bill_excel(
                preset_key, header_data, detail_rows, output_dir
            )

            get_logger().info(
                "Excel bill generated: preset=%s, bill_no=%s, detail_rows=%d, path=%s",
                preset_key, bill_no, len(detail_rows), path,
            )

            return send_file(
                path,
                as_attachment=True,
                download_name=os.path.basename(path),
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except ValueError as e:
            get_logger().error('Excel单据错误: %s', e, exc_info=True)
            return jsonify({"error": GENERIC_ERROR}), 400
        except Exception as e:
            get_logger().error("Excel bill generation failed: %s", e, exc_info=True)
            return jsonify({"error": GENERIC_ERROR}), 500
