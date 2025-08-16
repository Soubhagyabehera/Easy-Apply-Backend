from fastapi import APIRouter
from app.api.endpoints import jobs, users, photo_editor, pdf_tools, signature_creator, document_scanner, format_converter, size_optimizer, document_manager

api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(photo_editor.router, prefix="/photo-editor", tags=["photo-editor"])
api_router.include_router(pdf_tools.router, prefix="/pdf-tools", tags=["pdf-tools"])
api_router.include_router(signature_creator.router, prefix="/signature-creator", tags=["signature-creator"])
api_router.include_router(document_scanner.router, prefix="/document-scanner", tags=["document-scanner"])
api_router.include_router(format_converter.router, prefix="/format-converter", tags=["format-converter"])
api_router.include_router(size_optimizer.router, prefix="/size-optimizer", tags=["size-optimizer"])
api_router.include_router(document_manager.router, prefix="/document-manager", tags=["document-manager"])
