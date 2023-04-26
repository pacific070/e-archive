from django.urls import path
from EmployeeApp import views
urlpatterns = [
    path('logout', views.logoutView, name="employee_logout"),
    path('dashboard', views.dashboardView, name="employee_dashboard"),
    path('manage_tickets', views.manageDocumentsView,
         name="employee_manage_Documents"),
    path('tickets_report', views.ticketReportView,
         name="employee_tickets_report"),
    path('update_issue_status', views.updateDocumentstatusView,
         name="employee_update_issue_status"),
    path('issue_analytics', views.issueAnalyticsView,
         name="employee_issue_analytics"),
    path('issue_average_time_analytics', views.issueAverageTimeAnalyticsView,
         name="employee_issue_average_time_analytics"),
    path('ticket_report_average_time', views.ticketReportAverateTimeView,
         name="employee_ticket_report_average_time"),
    path('update_profile', views.updateProfileView,
         name="employee_update_profile"),
    path('download_ticket_report/<str:id>',
         views.download_ticket_report, name="employee_download_ticket_report"),
    # department
    path('manage_issue_type', views.manageIssueTypeView,
         name="employee_manage_issue_type"),
    path('updateissue_type', views.updateIssueTypeView,
         name="employee_update_issue_type"),
    # engineer
    path('manage_engineers', views.manageEngineerView,
         name="employee_manage_engineers"),
    path('update_engineer', views.updateEngineerView,
         name="employee_update_engineers"),

]
