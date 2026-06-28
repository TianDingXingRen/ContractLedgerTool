from routes import procurement_bp
from utils.errors import GENERIC_ERROR


def test_procurement_error_classification_exposes_user_errors():
    assert procurement_bp._classified_error_message(ValueError('数量格式无效')) == (
        '数量格式无效',
        False,
    )
    assert procurement_bp._classified_error_message(FileNotFoundError('文件不存在')) == (
        '文件不存在',
        False,
    )
    assert procurement_bp._classified_error_message('请先确认成交建议') == (
        '请先确认成交建议',
        False,
    )


def test_procurement_error_classification_hides_system_errors():
    assert procurement_bp._classified_error_message(RuntimeError('database exploded')) == (
        GENERIC_ERROR,
        True,
    )
