from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import logout as log_out
# Create your views here.
from django.db.models import Q, Count, F, Sum, Avg
from django.db import transaction
from datetime import datetime, timedelta
from MainApp.models import Documents, DocumentsType, Auth, Engineer, Documents_SELECT_RELATED
from django.template.loader import render_to_string, get_template
import json
from xhtml2pdf import pisa
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.serializers.json import DjangoJSONEncoder
from django.core.serializers import serialize
import re
from django.conf import settings
DEFAULT_PAGE = settings.DEFAULT_PAGE
DEFAULT_PER_PAGE = settings.DEFAULT_PER_PAGE


class LazyEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime("%m/%d/%Y, %H:%M %a")
        return super().default(obj)


def logoutView(request):
    log_out(request)
    return HttpResponseRedirect(reverse("login"))


def dashboardView(request):
    today = datetime.now().date()
    Documents = Documents.objects.select_related(Documents_SELECT_RELATED).filter(
        issue_type__department=request.user.employee.department)
    issue_status_count = Documents.aggregate(
        unassigned_issue=(Count('id', filter=Q(status="Unassigned"))),
        assigned_issue=(Count('id', filter=Q(status="Assigned"))),
        completed_issue=(Count('id', filter=Q(status="Completed"))),
        rejected_issue=(Count('id', filter=Q(status="Rejected"))),
        today_raised=(Count('id', filter=Q(
            status="Unassigned", issue_date__date=today))),
        today_resolved=(Count('id', filter=Q(
            status="Completed", resolved_date__date=today))),
    )
    issue_type_count = Documents.values(
        'issue_type__name', 'issue_type__department__name').annotate(count=Count('id'))
    return render(request, 'Employee/dashboard.html', {"issue_type_count": issue_type_count, "issue_status_count": issue_status_count})


def manageDocumentsView(request):
    # sourcery skip: extract-method, last-if-guard, remove-pass-body
    if request.method == "POST":
        try:
            issue_id = request.POST.get("issue_id", None)
            engineer_id = request.POST.get("engineer_id", None)
            if not issue_id:
                messages.error(request, "Required ticket id")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
            if not engineer_id:
                messages.error(request, "Select Service engineer")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
            with transaction.atomic():
                issue = Documents.objects.get(id=issue_id)
                assign_engineer = Engineer.objects.get(
                    id=engineer_id, department=issue.issue_type.department)
                if issue.status == "Completed":
                    messages.error(
                        request, "Ticket already completed! Service engineer can't be assign")
                    return HttpResponseRedirect(reverse('employee_manage_Documents'))
                if issue.status == "Rejected":
                    messages.error(
                        request, "Ticket already rejected! Service engineer can't be assign")
                    return HttpResponseRedirect(reverse('employee_manage_Documents'))
                if issue.assign_engineer != assign_engineer:
                    issue.assign_engineer = assign_engineer
                    issue.assigned_by = request.user
                    if issue.status == "Unassigned":
                        issue.status = "Assigned"
                        issue.assigned_date = datetime.now()
                    issue.save()
                    messages.success(
                        request, "Service engineer assigned successfully")
                else:
                    messages.error(
                        request, f"Service engineer {assign_engineer.auth.name} already assigned")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse('employee_manage_Documents'))
    else:
        f = Q(issue_type__department=request.user.employee.department)
        if from_date := request.GET.get('from_date', ''):
            from_date = datetime.strptime(from_date, '%Y-%m-%d')
            f &= Q(created_at__date__gte=from_date)
        if to_date := request.GET.get('to_date', ''):
            to_date = datetime.strptime(to_date, '%Y-%m-%d')
            f &= Q(created_at__date__lte=to_date)
        if ticket_status := request.GET.get('ticket_status', ''):
            f &= Q(status=ticket_status)
            if action_date := request.GET.get('action_date', ''):
                action_date = datetime.strptime(action_date, '%Y-%m-%d').date()
                if ticket_status == "Completed":
                    f &= Q(resolved_date__date=action_date)
                elif ticket_status == "Unassigned":
                    f &= Q(created_at__date=action_date)

        if issue_type := request.GET.get('issue_type', ''):
            f &= Q(issue_type__name=issue_type)

        ob_list = ['ticket_no', 'created_at', 'emp_name', 'assign_engineer__auth__name', 'issue_type__name', 'status', '-ticket_no',
                   '-created_at', '-emp_name', '-assign_engineer__auth__name', '-issue_type__name', '-status']
        order_by = request.GET.get('order_by', None)
        if not order_by or order_by not in ob_list:
            order_by = '-ticket_no'
        if query := request.GET.get('query', ''):
            f &= Q(Q(ticket_no__icontains=query) |
                   Q(location__icontains=query) |
                   Q(emp_organization__icontains=query) |
                   Q(assign_name__icontains=query) |
                   Q(assign_phone__icontains=query) |
                   Q(emp_name__icontains=query) |
                   Q(emp_phone__icontains=query))
        Documents_list = Documents.objects.filter(f).order_by(order_by)
        page = request.GET.get('page', DEFAULT_PAGE)
        paginator = Paginator(Documents_list, DEFAULT_PER_PAGE)
        try:
            Documents = paginator.page(page)
        except PageNotAnInteger:
            Documents = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            Documents = paginator.page(paginator.num_pages)

        engineers = Engineer.objects.select_related(
            'department', 'auth').all().order_by('auth__name')
        issue_types = DocumentsType.objects.filter(
            department=request.user.employee.department).order_by('name')
        context = {
            "Documents": Documents,
            "engineers": engineers,
            "issue_types": issue_types,
            "from_date": from_date,
            "to_date": to_date,
            "ticket_status": ticket_status,
            "issue_type": issue_type,
            "query": query,
            "order_by": order_by,
            "page": page
        }
        return render(request, 'Employee/manage_Documents.html', context)


def updateDocumentstatusView(request):  # sourcery skip: last-if-guard
    if request.method == "POST":
        try:
            issue_id = request.POST.get("issue_id", None)
            status = request.POST.get("status", None)
            if not issue_id:
                messages.error(request, "Required issue id")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
            if not status:
                messages.error(request, "Required issue status")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
            with transaction.atomic():
                issue = Documents.objects.get(id=issue_id)
                if issue.assign_engineer is None:
                    messages.error(
                        request, "To update ticket status first assign a service engineer.")
                    return HttpResponseRedirect(reverse('employee_manage_Documents'))
                if issue.status in ['Completed', "Rejected"]:
                    messages.error(
                        request, f"Failed to update. Ticket was already {issue.status} !")
                    return HttpResponseRedirect(reverse('employee_manage_Documents'))

                if issue.status in ["Assigned", "Rejected"] and status == "Completed":
                    issue.status = "Completed"
                    issue.resolved_date = datetime.now()
                    issue.resolved_by = request.user
                    issue.rejected_date = None
                    issue.rejected_reason = None

                elif issue.status == "Assigned" and status == "Rejected":
                    if rejected_reason := request.POST.get("rejected_reason", None):
                        issue.status = "Rejected"
                        issue.rejected_date = datetime.now()
                        issue.rejected_by = request.user
                        issue.rejected_reason = rejected_reason
                        issue.resolved_date = None
                    else:
                        messages.error(request, "Required rejected reason.")
                        return HttpResponseRedirect(reverse('employee_manage_Documents'))

                elif issue.status == "Rejected" and status == "Rejected":
                    if rejected_reason := request.POST.get("rejected_reason", None):
                        issue.rejected_reason = rejected_reason
                    else:
                        messages.error(request, "Required rejected reason.")
                        return HttpResponseRedirect(reverse('employee_manage_Documents'))

                elif issue.status == "Rejected" and status == "Assigned":
                    issue.status = "Assigned"
                    issue.assigned_by = request.user
                    issue.resolved_date = None
                    issue.resolved_by = None
                    issue.rejected_date = None
                    issue.rejected_by = None
                    issue.rejected_reason = None
                issue.save()
                messages.success(request, "Ticket status updated successfully")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse('employee_manage_Documents'))
    else:
        messages.error(request, "Invalid Request! Require Post Method")
        return HttpResponseRedirect(reverse('employee_manage_Documents'))


def ticketReportView(request):
    if request.method == "POST":
        messages.error(request, "Invalid Method POST")
        return HttpResponseRedirect(reverse('employee_tickets_report'))
    else:
        f = Q(issue_type__department=request.user.employee.department)
        if from_date := request.GET.get('from_date', ''):
            from_date = datetime.strptime(from_date, '%Y-%m-%d')
            f &= Q(created_at__date__gte=from_date)
        if to_date := request.GET.get('to_date', ''):
            to_date = datetime.strptime(to_date, '%Y-%m-%d')
            f &= Q(created_at__date__lte=to_date)
        if ticket_status := request.GET.get('ticket_status', ''):
            f &= Q(status=ticket_status)

        if issue_type := request.GET.get('issue_type', ''):
            f &= Q(issue_type__name=issue_type)

        if department := request.GET.get('department', ''):
            f &= Q(issue_type__department__name=department)

        ob_list = ['ticket_no', 'created_at', 'emp_name', 'assign_engineer__auth__name', 'issue_type__name', 'status', '-ticket_no',
                   '-created_at', '-emp_name', '-assign_engineer__auth__name', '-issue_type__name', '-status']
        order_by = request.GET.get('order_by', None)

        if not order_by or order_by not in ob_list:
            order_by = '-ticket_no'

        if query := request.GET.get('query', ''):
            f &= Q(Q(ticket_no__icontains=query) |
                   Q(location__icontains=query) |
                   Q(emp_organization__icontains=query) |
                   Q(assign_name__icontains=query) |
                   Q(assign_phone__icontains=query) |
                   Q(emp_name__icontains=query) |
                   Q(emp_phone__icontains=query))
        Documents_list = Documents.objects.filter(f).order_by(order_by)
        page = request.GET.get('page', DEFAULT_PAGE)
        paginator = Paginator(Documents_list, DEFAULT_PER_PAGE)
        try:
            Documents = paginator.page(page)
        except PageNotAnInteger:
            Documents = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            Documents = paginator.page(paginator.num_pages)
        josn_issue = serialize('json', Documents_list, cls=LazyEncoder)
        issue_types = DocumentsType.objects.filter(
            department=request.user.employee.department).order_by('name')
        context = {
            "Documents": Documents,
            "from_date": from_date,
            "to_date": to_date,
            "issue_types": issue_types,
            "issue_type": issue_type,
            "ticket_status": ticket_status,
            "query": query,
            "order_by": order_by,
            "page": page,
            "Documents_list_json": json.dumps(josn_issue)
        }
        return render(request, 'Employee/Documents_report.html', context)


@csrf_exempt
def issueAnalyticsView(request):
    if request.method != "POST":
        return JsonResponse({'success': False, 'message': "required post method"})
    try:
        from_date = (datetime.now() - timedelta(days=6)).date()
        to_date = datetime.now().date()
        date_list = [from_date + timedelta(days=x)
                     for x in range((to_date - from_date).days + 1)]
        issue_graph = Documents.objects.filter(issue_type__department=request.user.employee.department, created_at__date__gte=from_date, created_at__date__lte=to_date).values(
            'created_at__date').annotate(
            unassigned_issue=(Count('id', filter=Q(created_at__isnull=False))),
            assigned_issue=(
                Count('id', filter=Q(assigned_date__isnull=False))),
            completed_issue=(
                Count('id', filter=Q(resolved_date__isnull=False))),
            rejected_issue=(
                Count('id', filter=Q(rejected_date__isnull=False))),

        )
        labels, unassigned, assigned, completed, rejected = (
            [] for _ in range(5))

        def finddata(date):
            isu = list(filter(None, [
                value if value['created_at__date'] == date else {} for value in issue_graph]))
            if isu:
                unassigned.append(isu[0]['unassigned_issue'])
                assigned.append(isu[0]['assigned_issue'])
                completed.append(isu[0]['completed_issue'])
                rejected.append(isu[0]['rejected_issue'])
            else:
                unassigned.append(0)
                assigned.append(0)
                completed.append(0)
                rejected.append(0)
            labels.append(date.strftime('%d-%b'))
            return None

        list(map(finddata, date_list))

        Documents_status_series = [
            {'name': 'Unassigned', 'data': unassigned},
            {'name': 'Assigned', 'data': assigned},
            {'name': 'Completed', 'data': completed},
            {'name': 'Rejected', 'data': rejected}
        ]
        data = {'labels': labels,
                'Documents_status_series': Documents_status_series}
        return JsonResponse({'success': True, 'data': data})
    except Exception as e:
        return JsonResponse({'success': False, 'message': e})


@csrf_exempt
def issueAverageTimeAnalyticsView(request):
    if request.method != "POST":
        return JsonResponse({'success': False, 'message': "required post method"})
    try:
        Documents = Documents.objects.select_related(Documents_SELECT_RELATED).filter(issue_type__department=request.user.employee.department).values(
            'issue_type__name').annotate(
            raised_resolved=(Avg((F('resolved_date') - F('created_at')),
                             filter=Q(resolved_date__isnull=False))),
            raised_assigned=(Avg((F('assigned_date') - F('created_at')),
                             filter=Q(assigned_date__isnull=False))),
            assigned_resolved=(Avg((F('resolved_date') - F('assigned_date')),
                               filter=Q(resolved_date__isnull=False, assigned_date__isnull=False))),
            assigned_rejected=(Avg((F('rejected_date') - F('assigned_date')),
                               filter=Q(rejected_date__isnull=False, assigned_date__isnull=False))),
        )

        labels = []
        raised_resolved_series = []
        raised_assigned_series = []
        assigned_resolved_series = []
        assigned_rejected_series = []

        for i in Documents:
            labels.append(i['issue_type__name'])
            raised_resolved_series.append(
                int(i['raised_resolved'].total_seconds() / 3600) if i['raised_resolved'] else 0)
            raised_assigned_series.append(
                int(i['raised_assigned'].total_seconds() / 3600) if i['raised_assigned'] else 0)
            assigned_resolved_series.append(int(
                i['assigned_resolved'].total_seconds() / 3600) if i['assigned_resolved'] else 0)
            assigned_rejected_series.append(int(
                i['assigned_rejected'].total_seconds() / 3600) if i['assigned_rejected'] else 0)

        data = {'labels': labels,
                "series": [{
                    "name": 'Raised - Assigned',
                    "data": raised_assigned_series
                }, {
                    "name": 'Assigned - Resolved',
                    "data": assigned_resolved_series
                },
                    {
                        "name": 'Raised - Resolved',
                        "data": raised_resolved_series
                },
                    {
                        "name": 'Assigned - Rejected',
                        "data": assigned_rejected_series
                }]
                }
        return JsonResponse({'success': True, 'data': data})
    except Exception as e:
        return JsonResponse({'success': False, 'message': e})


def updateProfileView(request):  # sourcery skip: last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", '').strip()
            password = request.POST.get("password", '').strip()
            if not name:
                messages.error(request, "Required Name")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
            with transaction.atomic():
                user = request.user
                user.name = name
                pwd_change = False
                if password:
                    user.set_password(password)
                    pwd_change = True
                user.save()
                if pwd_change:
                    log_out(request)
                    return HttpResponseRedirect(reverse('login'))
                messages.success(request, "Profile Updated successfullly")
                return HttpResponseRedirect(reverse('employee_manage_Documents'))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse('employee_manage_Documents'))
    else:
        messages.error(request, "Invalid Request! Require Post Method")
        return HttpResponseRedirect(reverse('employee_manage_Documents'))


def download_ticket_report(request, id):
    issue = Documents.objects.get(id=id)
    context = {'issue': issue, "host_name": request.build_absolute_uri('/')}
    template = get_template('Employee/report_pdf.html')
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    filename = f"nsl_ticker_report{issue.ticket_no}.pdf"
    response['Content-Disposition'] = f'filename={filename}'
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Failed to download template.', status=200)
    return response


def ticketReportAverateTimeView(request):
    if request.method == "POST":
        messages.error(request, "Invalid Method POST")
        return HttpResponseRedirect(reverse('employee_tickets_report'))
    else:
        f = Q()
        filter_type = request.GET.get('filter_type', 'Raised_Assigned')
        ticket_type = request.GET.get('ticket_type', '')
        filter_type_list = [
            'Raised_Assigned', 'Assigned_Resolved', 'Raised_Resolved', 'Assigned_Rejected']
        if filter_type in filter_type_list:
            if filter_type == "Raised_Assigned":
                f &= Q(assigned_date__isnull=False)
            elif filter_type == "Assigned_Resolved":
                f &= Q(assigned_date__isnull=False,
                       resolved_date__isnull=False)
            elif filter_type == "Assigned_Rejected":
                f &= Q(assigned_date__isnull=False,
                       rejected_date__isnull=False)
            else:
                f &= Q(assigned_date__isnull=False,
                       resolved_date__isnull=False)
            f &= Q(issue_type__name=ticket_type)
            Documents_list = Documents.objects.filter(
                f).order_by('-created_at')
            page = request.GET.get('page', DEFAULT_PAGE)
            paginator = Paginator(Documents_list, DEFAULT_PER_PAGE)
            try:
                Documents = paginator.page(page)
            except PageNotAnInteger:
                Documents = paginator.page(DEFAULT_PAGE)
            except EmptyPage:
                Documents = paginator.page(paginator.num_pages)
            context = {
                "Documents": Documents,
                "filter_type": filter_type,
                "ticket_type": ticket_type
            }
            return render(request, 'Employee/Documents_report_avg_time.html', context)
        else:
            messages.error(
                request, f"Check Valid Filter Filter Type: {filter_type}")
            return HttpResponseRedirect(reverse('employee_tickets_report'))


#  ############### manage Department

def manageIssueTypeView(request):
    # sourcery skip: extract-method, last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", None)
            if not name:
                messages.error(request, "Required Issue Type name")
                return HttpResponseRedirect(reverse('employee_manage_issue_type'))
            if DocumentsType.objects.filter(name=name, department=request.user.employee.department).exists():
                messages.error(request, f"Issue TYpe name {name} exists")
                return HttpResponseRedirect(reverse('employee_manage_issue_type'))
            with transaction.atomic():
                DocumentsType.objects.create(
                    name=name, department=request.user.employee.department)
                messages.success(
                    request, f"Issue Type {name} created successfully")
                return HttpResponseRedirect(reverse('employee_manage_issue_type'))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse('employee_manage_issue_type'))
    else:
        f = Q(department=request.user.employee.department)
        ob_list = ['name', 'created_at', '-created_at', '-name']
        order_by = request.GET.get('order_by', None)
        if not order_by or order_by not in ob_list:
            order_by = '-created_at'
        if query := request.GET.get('query', ''):
            f &= Q(name__icontains=query)
        issue_type_list = DocumentsType.objects.filter(f).order_by(order_by)
        page = request.GET.get('page', DEFAULT_PAGE)
        paginator = Paginator(issue_type_list, DEFAULT_PER_PAGE)
        try:
            issue_types = paginator.page(page)
        except PageNotAnInteger:
            issue_types = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            issue_types = paginator.page(paginator.num_pages)
        context = {
            "issue_types": issue_types,
            "query": query,
            "order_by": order_by,
            "page": page
        }
        return render(request, 'Employee/manage_issue_type.html', context)


def updateIssueTypeView(request):
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse('employee_manage_departments'))
    try:
        name = request.POST.get("name", None)
        issue_type_id = request.POST.get("issue_type_id", None)
        if not name and not issue_type_id:
            messages.error(request, "Required All fields")
            return HttpResponseRedirect(reverse('employee_manage_issue_type'))
        if DocumentsType.objects.filter(name=name, department=request.user.employee.department).exists():
            messages.error(request, f"Issue Type name {name} exists")
            return HttpResponseRedirect(reverse('employee_manage_issue_type'))
        with transaction.atomic():
            issue_type = DocumentsType.objects.get(id=issue_type_id)
            issue_type.name = name
            issue_type.save()
            messages.success(
                request, f"Issue Type {name} updated successfully")
            return HttpResponseRedirect(reverse('employee_manage_issue_type'))
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(reverse('employee_manage_issue_type'))


# manage Employee

def manageEngineerView(request):  # sourcery skip: extract-method, last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", '').strip()
            email = request.POST.get("email", '').strip()
            phone = request.POST.get("phone", '').strip()
            password = request.POST.get("password", '').strip()
            print([name, email, phone, password])
            if not all([name, email, phone, password]):
                messages.error(request, "Required all fileds")
                return HttpResponseRedirect(reverse('employee_manage_engineers'))
            if not phone.isdigit():
                messages.error(
                    request, "Phone number must be contains only digits")
                return HttpResponseRedirect(reverse('employee_manage_engineers'))
            if len(phone) != 10:
                messages.error(request, "Phone nummber should be 10 digits")
                return HttpResponseRedirect(reverse('employee_manage_engineers'))
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                messages.error(request, "Invalid email format")
                return HttpResponseRedirect(reverse('employee_manage_engineers'))

            if Auth.objects.filter(email=email).exists():
                messages.error(request, f"Email {email} exists")
                return HttpResponseRedirect(reverse('employee_manage_engineers'))
            with transaction.atomic():
                department = request.user.employee.department
                user = Auth.objects.create_user(
                    name=name, email=email, password=password, user_type="Engineer", is_active=True)
                user.engineer.department = department
                user.engineer.phone = phone
                user.save()
                messages.success(
                    request, f"Engineer {name} created successfully")
                return HttpResponseRedirect(reverse('employee_manage_engineers'))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
    else:
        f = Q(department=request.user.employee.department)
        ob_list = ['auth__name', 'created_at', 'auth__email', 'phone' 'department__name' '-created_at',
                   '-auth__name', '-auth__email', 'department__name', '-phone']
        order_by = request.GET.get('order_by', None)
        if not order_by or order_by not in ob_list:
            order_by = '-created_at'
        if query := request.GET.get('query', ''):
            f &= Q(Q(auth__name__icontains=query) |
                   Q(auth__email__icontains=query) |
                   Q(phone__icontains=query))
        engineer_list = Engineer.objects.select_related(
            'auth').filter(f).order_by(order_by)
        page = request.GET.get('page', DEFAULT_PAGE)
        paginator = Paginator(engineer_list, DEFAULT_PER_PAGE)
        try:
            engineers = paginator.page(page)
        except PageNotAnInteger:
            engineers = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            engineers = paginator.page(paginator.num_pages)
        context = {
            "engineers": engineers,
            "query": query,
            "order_by": order_by,
            "page": page
        }
        return render(request, 'Employee/manage_engineer.html', context)


def updateEngineerView(request):  # sourcery skip: extract-method, last-if-guard
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse('employee_manage_engineers'))
    try:
        name = request.POST.get("name", '').strip()
        email = request.POST.get("email", '').strip()
        phone = request.POST.get("phone", '').strip()
        engineer_id = request.POST.get('engineer_id', '').strip()
        password = request.POST.get("password", '').strip()

        if not all([name, email, engineer_id, phone]):
            messages.error(request, "Required all fileds")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
        if not phone.isdigit():
            messages.error(
                request, "Phone number must be contains only digits")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
        if len(phone) != 10:
            messages.error(request, "Phone nummber should be 10 digits")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            messages.error(request, "Invalid email format")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
        if Auth.objects.filter(email=email).exclude(email=email).exists():
            messages.error(request, f"Email {email} exists")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
        with transaction.atomic():
            user = Engineer.objects.get(id=engineer_id).auth
            user.engineer.phone = phone
            user.name = name
            user.email = email
            if password:
                user.set_password(password)
            user.save()
            messages.success(
                request, f"Engineer {name} updated successfully")
            return HttpResponseRedirect(reverse('employee_manage_engineers'))
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(reverse('employee_manage_engineers'))
