class M1Error(Exception):
    pass

class TemplateNotFoundError(M1Error):
    pass

class ValidationError(M1Error):
    pass

class AssemblyError(M1Error):
    pass

class ExportError(M1Error):
    pass
