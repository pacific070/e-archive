from django.urls import path
from AdminApp import views

urlpatterns = [
    path("logout", views.logoutView, name="admin_logout"),
    path("dashboard", views.dashboardView, name="dashboard"),
    path("manage_documents", views.manageDocumentsView, name="manage_documents"),
    path("upload_document", views.uploadDocumentView, name="upload_document"),
    path("async_upload_document", views.asyncUploadDocumentView, name="async_upload_document"),
    path("tickets_report", views.ticketReportView, name="tickets_report"),
    path(
        "update_issue_status",
        views.updateDocumentstatusView,
        name="update_issue_status",
    ),
    path("issue_analytics", views.docsAnalyticsView, name="issue_analytics"),
    path(
        "issue_average_time_analytics",
        views.issueAverageTimeAnalyticsView,
        name="issue_average_time_analytics",
    ),
    path(
        "ticket_report_average_time",
        views.ticketReportAverateTimeView,
        name="ticket_report_average_time",
    ),
    path("update_profile", views.updateProfileView, name="update_profile"),
    path(
        "download_ticket_report/<str:id>",
        views.download_ticket_report,
        name="download_ticket_report",
    ),
    # department
    path("manage_departments", views.manageDepartmentView, name="manage_departments"),
    path("update_department", views.updateDepartmentView, name="update_department"),
    # category
    path("manage_category", views.manageCategoryView, name="manage_category"),
    path("update_category", views.updateCategoryView, name="update_category"),
    # subcategory
    path(
        "manage_sub_category/<str:category_id>",
        views.manageSubCategoryView,
        name="manage_sub_category",
    ),
    path(
        "update_sub_category/<str:category_id>",
        views.updateSubCategoryView,
        name="update_sub_category",
    ),
    # sub Type
    path("manage_sub_type", views.manageSubtypeView, name="manage_sub_type"),
    path("update_sub_type", views.updateSubtypeView, name="update_sub_type"),
    path("filter_department_change", views.filter_department_change, name="filter_department_change"),
    path("filter_category_change", views.filter_category_change, name="filter_category_change"),
    # employee
    path("manage_employees", views.manageEmployeeView, name="manage_employees"),
    path("update_employee", views.updateEmployeeView, name="update_employee"),
]
