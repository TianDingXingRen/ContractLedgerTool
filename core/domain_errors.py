"""Framework-neutral application errors shared by services and HTTP adapters."""


class DomainError(Exception):
    status_code = 400
    default_message = '操作失败'

    def __init__(self, message=None, *, detail=None):
        super().__init__(message or self.default_message)
        self.public_message = message or self.default_message
        self.detail = detail


class ValidationError(DomainError):
    status_code = 400
    default_message = '请求参数无效'


class NotFoundError(DomainError):
    status_code = 404
    default_message = '请求的资源不存在'


class ConflictError(DomainError):
    status_code = 409
    default_message = '当前数据状态存在冲突'


class ExternalToolError(DomainError):
    status_code = 500
    default_message = '外部文档工具执行失败'


class DocumentGenerationError(ExternalToolError):
    default_message = '合同生成失败，请检查模板和填写内容'

    def __init__(self, errors):
        self.errors = list(errors or [])
        super().__init__(self.default_message, detail='; '.join(self.errors))


class ProcurementLinkError(DomainError):
    status_code = 500
    default_message = '采购项目关联失败'
