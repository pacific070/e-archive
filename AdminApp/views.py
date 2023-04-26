from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import logout as log_out
import os
from django.core.files.storage import FileSystemStorage

# Create your views here.
from django.db.models import Q, Count, F, Sum, Avg
from django.db import transaction
from datetime import datetime, timedelta
from MainApp.models import (
    Department,
    Category,
    SubCategory,
    SubType,
    UploadMedia,
    Documents,
    Auth,
    Employee,
    DOCUMENTS_SELECT_RELATED,
)
from django.template.loader import get_template
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
    documents = Documents.objects.select_related(DOCUMENTS_SELECT_RELATED)
    docs_status_count = documents.aggregate(
        pending_docs=(Count("id", filter=Q(status="Pending"))),
        approved_docs=(Count("id", filter=Q(status="Approved"))),
        rejected_docs=(Count("id", filter=Q(status="Rejected"))),
        today_upload=(Count("id", filter=Q(status="Pending", upload_on__date=today))),
        today_approved=(
            Count("id", filter=Q(status="Approved", upload_on__date=today))
        ),
    )
    docs_sub_type_count = documents.values(
        "subtype__name", "subtype__department__name"
    ).annotate(count=Count("id"))
    context = {
        "docs_sub_type_count": docs_sub_type_count,
        "docs_status_count": docs_status_count,
    }
    return render(request, "AdminApp/dashboard.html", context)


def manageDocumentsView(request):
    # sourcery skip: extract-method, last-if-guard, remove-pass-body
    if request.method == "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse("manage_documents"))
    else:
        f = Q()
        if status := request.GET.get("status", ""):
            f &= Q(status=status)
            if action_date := request.GET.get("action_date", ""):
                action_date = datetime.strptime(action_date, "%Y-%m-%d").date()
                if status == "Completed":
                    f &= Q(resolved_date__date=action_date)
                elif status == "Unassigned":
                    f &= Q(created_at__date=action_date)

        if sub_type := request.GET.get("sub_type", ""):
            f &= Q(subtype__name=sub_type)

        if department := request.GET.get("department", ""):
            f &= Q(subtype__department__name=department)

        if category := request.GET.get("category", ""):
            f &= Q(sub_category__category__name=category)

        if sub_category := request.GET.get("sub_category", ""):
            f &= Q(sub_category__name=sub_category)

        ob_list = [
            "documet_no",
            "created_at",
            "upload_by__name",
            "sub_type__name",
            "sub_type__department__name",
            "sub_category__name",
            "sub_category__category__name",
            "status",

            "-documet_no",
            "-created_at",
            "-upload_by__name",
            "-sub_type__name",
            "-sub_type__department__name",
            "-sub_category__name",
            "-sub_category__category__name",
            "-status",
        ]
        order_by = request.GET.get("order_by", None)
        if not order_by or order_by not in ob_list:
            order_by = "-document_no"
        if query := request.GET.get("query", ""):
            f &= Q(
                Q(ticket_no__icontains=query)
                | Q(location__icontains=query)
                | Q(emp_organization__icontains=query)
                | Q(assign_name__icontains=query)
                | Q(assign_phone__icontains=query)
                | Q(emp_name__icontains=query)
                | Q(emp_phone__icontains=query)
            )
        documents_list = Documents.objects.filter(f).order_by(order_by)
        page = request.GET.get("page", DEFAULT_PAGE)
        paginator = Paginator(documents_list, DEFAULT_PER_PAGE)
        try:
            documents = paginator.page(page)
        except PageNotAnInteger:
            documents = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            documents = paginator.page(paginator.num_pages)

        departments = Department.objects.all().order_by("name")
        sub_types = (
            SubType.objects.select_related("department")
            .filter(department__name=department)
            .order_by("name")
        )
        categories = (
            Category.objects.select_related("department")
            .filter(department__name=department)
            .order_by("name")
        )
        sub_categories = (
            SubCategory.objects.select_related("category")
            .filter(category__name=category)
            .order_by("name")
        )
        context = {
            "documents": documents,
            "departments": departments,
            "categories": categories,
            "sub_categories": sub_categories,
            "sub_types":sub_types,

            "status": status,
            "sub_type": sub_type,
            "sub_category": sub_category,
            "category": category,
            "department": department,
            "query": query,
            "order_by": order_by,
            "page": page,
        }
        return render(request, "AdminApp/manage_document.html", context)


def uploadDocumentView(request):  # sourcery skip: last-if-guard
    if request.method == "POST":
        messages.error(request, "Invalid method")
        return HttpResponseRedirect(reverse("manage_documents"))
    else:
        departments = Department.objects.all().order_by("name")
        context = {
            "departments": departments
        }
        return render(request, "AdminApp/upload_document.html", context)
    
@csrf_exempt
def asyncUploadDocumentView(request):
    if request.method not in ["POST", "FILES"]:
        resp_data = {"success": False, "message": "Required POST Method"}
        return JsonResponse(resp_data)
    try:
        data = request.POST
        file = request.FILES
        department = data.get("department", None)
        category = data.get("category", None)
        sub_category = data.get("sub_category", None)
        sub_type = data.get("sub_type", None)
        version = data.get("version", None)
        description = data.get("description", None)
        media = file.get("media", None)
        print(request.headers)
        print('data', [department, category, sub_category, sub_type, version, description, media])
        if not all([department, category, sub_category, sub_type, version, description, media]):
            resp_data = {"success": False, "message": "Required All Fields"}
            return JsonResponse(resp_data)
        with transaction.atomic():
            sub_category_instance = SubCategory.objects.get(name = sub_category)
            sub_type_instance = SubType.objects.get(name = sub_type)
            fs = FileSystemStorage()
            # rename the file here
            file_ext = media.name.split('.')[-1]
            filename = f'{sub_category_instance.category.category_no}_{sub_category_instance.sub_category_no}_{sub_type_instance.subtype_no}_{100000+Documents.objects.all().count()}_{version}.{file_ext}'
            file = fs.save(filename, media)

            content_type = media.content_type
            file_size = media.size
            sub_path = os.path.join(sub_type_instance.department.name, sub_category_instance.category.name, sub_category_instance.name)
            
            media_instance = UploadMedia.objects.create( file_name = filename, file_size = file_size, content_type = content_type, sub_path = sub_path)

            document = Documents.objects.create(media = media_instance, sub_category = sub_category_instance, subtype = sub_type_instance,version = version, description = description, upload_by = request.user, upload_on = datetime.now(), modify_on = datetime.now())
            resp_data = {
                "success": True,
                "message": "Document upload successfully",
                "document_number": document.document_no,
            }
            return JsonResponse(resp_data)

    except Exception as e:
        print("erroe", e)
        resp_data = {"success": False, "message": f"{e}"}
        return JsonResponse(resp_data)



def updateDocumentstatusView(request):  # sourcery skip: last-if-guard
    if request.method == "POST":
        try:
            issue_id = request.POST.get("issue_id", None)
            status = request.POST.get("status", None)
            if not issue_id:
                messages.error(request, "Required issue id")
                return HttpResponseRedirect(reverse("manage_Documents"))
            if not status:
                messages.error(request, "Required issue status")
                return HttpResponseRedirect(reverse("manage_Documents"))
            with transaction.atomic():
                issue = Documents.objects.get(id=issue_id)
                if issue.assign_engineer is None:
                    messages.error(
                        request,
                        "To update ticket status first assign a service engineer.",
                    )
                    return HttpResponseRedirect(reverse("manage_Documents"))
                if issue.status in ["Completed", "Rejected"]:
                    messages.error(
                        request,
                        f"Failed to update. Ticket was already {issue.status} !",
                    )
                    return HttpResponseRedirect(reverse("manage_Documents"))

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
                        return HttpResponseRedirect(reverse("manage_Documents"))

                elif issue.status == "Rejected" and status == "Rejected":
                    if rejected_reason := request.POST.get("rejected_reason", None):
                        issue.rejected_reason = rejected_reason
                    else:
                        messages.error(request, "Required rejected reason.")
                        return HttpResponseRedirect(reverse("manage_Documents"))

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
                return HttpResponseRedirect(reverse("manage_Documents"))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse("manage_Documents"))
    else:
        messages.error(request, "Invalid Request! Require Post Method")
        return HttpResponseRedirect(reverse("manage_Documents"))
    

def ticketReportView(request):
    if request.method == "POST":
        messages.error(request, "Invalid Method POST")
        return HttpResponseRedirect(reverse("tickets_report"))
    else:
        f = Q()
        if from_date := request.GET.get("from_date", ""):
            from_date = datetime.strptime(from_date, "%Y-%m-%d")
            f &= Q(created_at__date__gte=from_date)
        if to_date := request.GET.get("to_date", ""):
            to_date = datetime.strptime(to_date, "%Y-%m-%d")
            f &= Q(created_at__date__lte=to_date)
        if ticket_status := request.GET.get("ticket_status", ""):
            f &= Q(status=ticket_status)

        if issue_type := request.GET.get("issue_type", ""):
            f &= Q(issue_type__name=issue_type)

        if department := request.GET.get("department", ""):
            f &= Q(issue_type__department__name=department)

        ob_list = [
            "ticket_no",
            "created_at",
            "emp_name",
            "assign_engineer__auth__name",
            "issue_type__name",
            "status",
            "-ticket_no",
            "-created_at",
            "-emp_name",
            "-assign_engineer__auth__name",
            "-issue_type__name",
            "-status",
        ]
        order_by = request.GET.get("order_by", None)

        if not order_by or order_by not in ob_list:
            order_by = "-ticket_no"

        if query := request.GET.get("query", ""):
            f &= Q(
                Q(ticket_no__icontains=query)
                | Q(location__icontains=query)
                | Q(emp_organization__icontains=query)
                | Q(assign_name__icontains=query)
                | Q(assign_phone__icontains=query)
                | Q(emp_name__icontains=query)
                | Q(emp_phone__icontains=query)
            )
        Documents_list = Documents.objects.filter(f).order_by(order_by)
        page = request.GET.get("page", DEFAULT_PAGE)
        paginator = Paginator(Documents_list, DEFAULT_PER_PAGE)
        try:
            Documents = paginator.page(page)
        except PageNotAnInteger:
            Documents = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            Documents = paginator.page(paginator.num_pages)
        josn_issue = serialize("json", Documents_list, cls=LazyEncoder)
        departments = Department.objects.all().order_by("name")
        issue_types = (
            DocumentsType.objects.select_related("department")
            .filter(department__name=department)
            .order_by("name")
        )
        context = {
            "Documents": Documents,
            "from_date": from_date,
            "to_date": to_date,
            "departments": departments,
            "department": department,
            "issue_type": issue_type,
            "issue_types": issue_types,
            "ticket_status": ticket_status,
            "query": query,
            "order_by": order_by,
            "page": page,
            "Documents_list_json": json.dumps(josn_issue),
        }
        return render(request, "AdminApp/manage_document.html", context)


@csrf_exempt
def docsAnalyticsView(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "required post method"})
    try:
        from_date = (datetime.now() - timedelta(days=6)).date()
        to_date = datetime.now().date()
        date_list = [
            from_date + timedelta(days=x) for x in range((to_date - from_date).days + 1)
        ]
        issue_graph = (
            Documents.objects.filter(
                created_at__date__gte=from_date, created_at__date__lte=to_date
            )
            .values("created_at__date")
            .annotate(
                pending_docs=(Count("id", filter=Q(status="Pending"))),
                appreved_docs=(Count("id", filter=Q(status="Approved"))),
                rejected_docs=(Count("id", filter=Q(status="Rejected"))),
            )
        )
        labels, pending, approved, rejected = ([] for _ in range(4))

        def finddata(date):
            isu = list(
                filter(
                    None,
                    [
                        value if value["created_at__date"] == date else {}
                        for value in issue_graph
                    ],
                )
            )
            if isu:
                pending.append(isu[0]["pending_docs"])
                approved.append(isu[0]["approved_docs"])
                rejected.append(isu[0]["rejected_docs"])
            else:
                pending.append(0)
                approved.append(0)
                rejected.append(0)
            labels.append(date.strftime("%d-%b"))
            return None

        list(map(finddata, date_list))

        docs_status_series = [
            {"name": "Pending", "data": pending},
            {"name": "Apprvoed", "data": approved},
            {"name": "Rejected", "data": rejected},
        ]
        data = {"labels": labels, "docs_status_series": docs_status_series}
        return JsonResponse({"success": True, "data": data})
    except Exception as e:
        return JsonResponse({"success": False, "message": e})


@csrf_exempt
def filter_department_change(request):
    if request.method != "POST":
        resp_data = {"success": False, "message": "Required POST Method"}
        return JsonResponse(resp_data)
    try:
        data = json.loads(request.body)
        department_name = data.get("department_name", None)
        if not department_name:
            resp_data = {"success": False, "message": "Required Department Name"}
            return JsonResponse(resp_data)
        with transaction.atomic():
            sub_types = (
                SubType.objects.select_related("department")
                .filter(department__name=department_name)
                .order_by("name")
                .values("id", "name")
            )
            categories = (
                Category.objects.select_related("department")
                .filter(department__name=department_name)
                .order_by("name")
                .values("id", "name")
            )
            resp_data = {
                "success": True,
                "message": "Issue types get successfully",
                "data": {
                    "categories" :list(categories),
                    "sub_types" :list(sub_types)
                }
            }
            return JsonResponse(resp_data)

    except Exception as e:
        resp_data = {"success": False, "message": f"{e}"}
        return JsonResponse(resp_data)

@csrf_exempt
def filter_category_change(request):
    if request.method != "POST":
        resp_data = {"success": False, "message": "Required POST Method"}
        return JsonResponse(resp_data)
    try:
        data = json.loads(request.body)
        category_name = data.get("category_name", None)
        if not category_name:
            resp_data = {"success": False, "message": "Required Category Name"}
            return JsonResponse(resp_data)
        with transaction.atomic():
            sub_categories = (
                SubCategory.objects.select_related("category")
                .filter(category__name=category_name)
                .order_by("name")
                .values("id", "name")
            )
            resp_data = {
                "success": True,
                "message": "Sub categories get successfully",
                "data": list(sub_categories),
            }
            return JsonResponse(resp_data)

    except Exception as e:
        resp_data = {"success": False, "message": f"{e}"}
        return JsonResponse(resp_data)


@csrf_exempt
def issueAverageTimeAnalyticsView(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "required post method"})
    try:
        Documents = (
            Documents.objects.select_related(DOCUMENTS_SELECT_RELATED)
            .values("issue_type__name")
            .annotate(
                raised_resolved=(
                    Avg(
                        (F("resolved_date") - F("created_at")),
                        filter=Q(resolved_date__isnull=False),
                    )
                ),
                raised_assigned=(
                    Avg(
                        (F("assigned_date") - F("created_at")),
                        filter=Q(assigned_date__isnull=False),
                    )
                ),
                assigned_resolved=(
                    Avg(
                        (F("resolved_date") - F("assigned_date")),
                        filter=Q(
                            resolved_date__isnull=False, assigned_date__isnull=False
                        ),
                    )
                ),
                assigned_rejected=(
                    Avg(
                        (F("rejected_date") - F("assigned_date")),
                        filter=Q(
                            rejected_date__isnull=False, assigned_date__isnull=False
                        ),
                    )
                ),
            )
        )

        labels = []
        raised_resolved_series = []
        raised_assigned_series = []
        assigned_resolved_series = []
        assigned_rejected_series = []

        for i in Documents:
            labels.append(i["issue_type__name"])
            raised_resolved_series.append(
                int(i["raised_resolved"].total_seconds() / 3600)
                if i["raised_resolved"]
                else 0
            )
            raised_assigned_series.append(
                int(i["raised_assigned"].total_seconds() / 3600)
                if i["raised_assigned"]
                else 0
            )
            assigned_resolved_series.append(
                int(i["assigned_resolved"].total_seconds() / 3600)
                if i["assigned_resolved"]
                else 0
            )
            assigned_rejected_series.append(
                int(i["assigned_rejected"].total_seconds() / 3600)
                if i["assigned_rejected"]
                else 0
            )

        data = {
            "labels": labels,
            "series": [
                {"name": "Raised - Assigned", "data": raised_assigned_series},
                {"name": "Assigned - Resolved", "data": assigned_resolved_series},
                {"name": "Raised - Resolved", "data": raised_resolved_series},
                {"name": "Assigned - Rejected", "data": assigned_rejected_series},
            ],
        }
        return JsonResponse({"success": True, "data": data})
    except Exception as e:
        return JsonResponse({"success": False, "message": e})


def updateProfileView(request):  # sourcery skip: last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", "").strip()
            password = request.POST.get("password", "").strip()
            if not name:
                messages.error(request, "Required Name")
                return HttpResponseRedirect(reverse("manage_documents"))
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
                    return HttpResponseRedirect(reverse("login"))
                messages.success(request, "Profile Updated successfullly")
                return HttpResponseRedirect(reverse("manage_documents"))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse("manage_documents"))
    else:
        messages.error(request, "Invalid Request! Require Post Method")
        return HttpResponseRedirect(reverse("manage_documents"))


def download_ticket_report(request, id):
    issue = Documents.objects.get(id=id)
    context = {"issue": issue, "host_name": request.build_absolute_uri("/")}
    template = get_template("AdminApp/report_pdf.html")
    html = template.render(context)
    response = HttpResponse(content_type="application/pdf")
    filename = f"nsl_ticker_report{issue.ticket_no}.pdf"
    response["Content-Disposition"] = f"filename={filename}"
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse("Failed to download template.", status=200)
    return response


def ticketReportAverateTimeView(request):
    if request.method == "POST":
        messages.error(request, "Invalid Method POST")
        return HttpResponseRedirect(reverse("tickets_report"))
    else:
        f = Q()
        filter_type = request.GET.get("filter_type", "Raised_Assigned")
        ticket_type = request.GET.get("ticket_type", "")
        filter_type_list = [
            "Raised_Assigned",
            "Assigned_Resolved",
            "Raised_Resolved",
            "Assigned_Rejected",
        ]
        if filter_type in filter_type_list:
            if filter_type == "Raised_Assigned":
                f &= Q(assigned_date__isnull=False)
            elif filter_type == "Assigned_Resolved":
                f &= Q(assigned_date__isnull=False, resolved_date__isnull=False)
            elif filter_type == "Assigned_Rejected":
                f &= Q(assigned_date__isnull=False, rejected_date__isnull=False)
            else:
                f &= Q(assigned_date__isnull=False, resolved_date__isnull=False)
            f &= Q(issue_type__name=ticket_type)
            Documents_list = Documents.objects.filter(f).order_by("-created_at")
            page = request.GET.get("page", DEFAULT_PAGE)
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
                "ticket_type": ticket_type,
            }
            return render(request, "AdminApp/Documents_report_avg_time.html", context)
        else:
            messages.error(
                request,
                f"Check Valid Filter Filter Type: {filter_type}, Ticket Type : {ticket_type}",
            )
            return HttpResponseRedirect(reverse("tickets_report"))


#  ############### manage Department


def manageDepartmentView(request):
    # sourcery skip: extract-method, last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", None)
            if not name:
                messages.error(request, "Required department name")
                return HttpResponseRedirect(reverse("manage_departments"))
            if Department.objects.filter(name=name).exists():
                messages.error(request, f"Department name {name} exists")
                return HttpResponseRedirect(reverse("manage_departments"))
            with transaction.atomic():
                Department.objects.create(name=name)
                messages.success(request, f"Department {name} created successfully")
                return HttpResponseRedirect(reverse("manage_departments"))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse("manage_departments"))
    else:
        f = Q()
        ob_list = ["name", "created_at", "-created_at", "-name"]
        order_by = request.GET.get("order_by", None)
        if not order_by or order_by not in ob_list:
            order_by = "-created_at"
        if query := request.GET.get("query", ""):
            f &= Q(name__icontains=query)
        department_list = Department.objects.filter(f).order_by(order_by)
        page = request.GET.get("page", DEFAULT_PAGE)
        paginator = Paginator(department_list, DEFAULT_PER_PAGE)
        try:
            departments = paginator.page(page)
        except PageNotAnInteger:
            departments = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            departments = paginator.page(paginator.num_pages)
        context = {
            "departments": departments,
            "query": query,
            "order_by": order_by,
            "page": page,
        }
        return render(request, "AdminApp/manage_department.html", context)


def updateDepartmentView(request):
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse("manage_departments"))
    try:
        name = request.POST.get("name", None)
        department_id = request.POST.get("department_id", None)
        if not name and not department_id:
            messages.error(request, "Required All fields")
            return HttpResponseRedirect(reverse("manage_departments"))
        if Department.objects.filter(name=name).exists():
            messages.error(request, f"Department name {name} exists")
            return HttpResponseRedirect(reverse("manage_departments"))
        with transaction.atomic():
            department = Department.objects.get(id=department_id)
            department.name = name
            department.save()
            messages.success(request, f"Department {name} updated successfully")
            return HttpResponseRedirect(reverse("manage_departments"))
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(reverse("manage_departments"))


## Category


def manageCategoryView(request):
    # sourcery skip: extract-method, last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", None)
            department_id = request.POST.get("department_id", None)
            if not name:
                messages.error(request, "Required Category name")
                return HttpResponseRedirect(reverse("manage_category"))
            if not department_id:
                messages.error(request, "Required department id")
                return HttpResponseRedirect(reverse("manage_category"))
            if Category.objects.filter(name=name, department=department_id).exists():
                messages.error(request, f"Category name {name} exists")
                return HttpResponseRedirect(reverse("manage_category"))
            with transaction.atomic():
                department = Department.objects.get(id=department_id)
                Category.objects.create(name=name, department=department)
                messages.success(request, f"Category {name} created successfully")
                return HttpResponseRedirect(reverse("manage_category"))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse("manage_category"))
    else:
        f = Q()
        ob_list = ["name", "created_at", "department__name", "-created_at", "-name", "-department__name"]
        order_by = request.GET.get("order_by", None)
        if not order_by or order_by not in ob_list:
            order_by = "-created_at"
        if query := request.GET.get("query", ""):
            f &= Q(name__icontains=query)
        if department := request.GET.get("department", ""):
            f &= Q(department__name=department)

        category_list = Category.objects.filter(f).order_by(order_by)
        page = request.GET.get("page", DEFAULT_PAGE)
        paginator = Paginator(category_list, DEFAULT_PER_PAGE)
        try:
            categories = paginator.page(page)
        except PageNotAnInteger:
            categories = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            categories = paginator.page(paginator.num_pages)
        departments = Department.objects.all().order_by("name")
        context = {
            "departments": departments,
            "categories": categories,
            "query": query,
            "department": department,
            "order_by": order_by,
            "page": page,
        }
        return render(request, "AdminApp/manage_category.html", context)


def updateCategoryView(request):
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse("manage_category"))
    try:
        name = request.POST.get("name", None)
        category_id = request.POST.get("category_id", None)
        if not name and not category_id:
            messages.error(request, "Required All fields")
            return HttpResponseRedirect(reverse("manage_category"))
        if Category.objects.filter(name=name).exists():
            messages.error(request, f"Category name {name} exists")
            return HttpResponseRedirect(reverse("manage_category"))
        with transaction.atomic():
            category = Category.objects.get(id=category_id)
            category.name = name
            category.save()
            messages.success(request, f"Category {name} updated successfully")
            return HttpResponseRedirect(reverse("manage_category"))
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(reverse("manage_category"))


## sub category


def manageSubCategoryView(request, category_id):
    if request.method == "POST":
        try:
            name = request.POST.get("name", None)
            if not name:
                messages.error(request, "Required Subcategory name")
                return HttpResponseRedirect(
                    reverse("manage_sub_category", kwargs={"category_id": category_id})
                )
            if SubCategory.objects.filter(name=name, category=category_id).exists():
                messages.error(request, f"Sub category name {name} exists")
                return HttpResponseRedirect(
                    reverse("manage_sub_category", kwargs={"category_id": category_id})
                )
            with transaction.atomic():
                category = Category.objects.get(id=category_id)
                SubCategory.objects.create(name=name, category=category)
                messages.success(request, f"Sub category {name} created successfully")
                return HttpResponseRedirect(
                    reverse("manage_sub_category", kwargs={"category_id": category_id})
                )
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(
                reverse("manage_sub_category", kwargs={"category_id": category_id})
            )
    else:
        sub_category_list = (
            SubCategory.objects.select_related("category")
            .filter(category=category_id)
            .order_by("-created_at")
        )
        return render(
            request,
            "AdminApp/manage_sub_category.html",
            {"sub_category_list": sub_category_list, "category_id": category_id},
        )


def updateSubCategoryView(request, category_id):
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(
            reverse("manage_sub_category", kwargs={"category_id": category_id})
        )
    try:
        name = request.POST.get("name", None)
        sub_category_id = request.POST.get("sub_category_id", None)
        if not name and not sub_category_id:
            messages.error(request, "Required all fileds")
            return HttpResponseRedirect(
                reverse("manage_sub_category", kwargs={"category_id": category_id})
            )
        if SubCategory.objects.filter(name=name, category=category_id).exists():
            messages.error(request, f"Sub category name {name} exists")
            return HttpResponseRedirect(
                reverse("manage_sub_category", kwargs={"category_id": category_id})
            )
        with transaction.atomic():
            subcategory = SubCategory.objects.get(id=sub_category_id)
            subcategory.name = name
            subcategory.save()
            messages.success(request, f"Sub category {name} updated successfully")
            return HttpResponseRedirect(
                reverse("manage_sub_category", kwargs={"category_id": category_id})
            )
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(
            reverse("manage_sub_category", kwargs={"category_id": category_id})
        )


## subType


def manageSubtypeView(request):
    # sourcery skip: extract-method, last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", None)
            department_id = request.POST.get("department_id", None)
            if not name:
                messages.error(request, "Required Sub type name")
                return HttpResponseRedirect(reverse("manage_sub_type"))
            if not department_id:
                messages.error(request, "Required department_id")
                return HttpResponseRedirect(reverse("manage_sub_type"))
            if SubType.objects.filter(name=name, department=department_id).exists():
                messages.error(request, f"Sub type name {name} exists")
                return HttpResponseRedirect(reverse("manage_sub_type"))
            with transaction.atomic():
                department = Department.objects.get(id=department_id)
                SubType.objects.create(name=name, department=department)
                messages.success(request, f"Sub type {name} created successfully")
                return HttpResponseRedirect(reverse("manage_sub_type"))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse("manage_sub_type"))
    else:
        f = Q()
        ob_list = ["name", "created_at", "department__name", "-created_at", "-name", "-department__name"]
        order_by = request.GET.get("order_by", None)
        if not order_by or order_by not in ob_list:
            order_by = "-created_at"
        if query := request.GET.get("query", ""):
            f &= Q(name__icontains=query)
        if department := request.GET.get("department", ""):
            f &= Q(department__name=department)

        sub_type_list = SubType.objects.filter(f).order_by(order_by)
        page = request.GET.get("page", DEFAULT_PAGE)
        paginator = Paginator(sub_type_list, DEFAULT_PER_PAGE)
        try:
            sub_types = paginator.page(page)
        except PageNotAnInteger:
            sub_types = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            sub_types = paginator.page(paginator.num_pages)
        departments = Department.objects.all().order_by('name')
        context = {
            "sub_types": sub_types,
            "departments": departments,
            "query": query,
            "department": department,
            "order_by": order_by,
            "page": page,
        }
        return render(request, "AdminApp/manage_sub_type.html", context)


def updateSubtypeView(request):
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse("manage_sub_type"))
    try:
        name = request.POST.get("name", None)
        sub_type_id = request.POST.get("sub_type_id", None)
        if not name and not sub_type_id:
            messages.error(request, "Required All fields")
            return HttpResponseRedirect(reverse("manage_sub_type"))
        if Department.objects.filter(name=name).exists():
            messages.error(request, f"Sub Type name {name} exists")
            return HttpResponseRedirect(reverse("manage_sub_type"))
        with transaction.atomic():
            sub_type = SubType.objects.get(id=sub_type_id)
            sub_type.name = name
            sub_type.save()
            messages.success(request, f"Sub Type {name} updated successfully")
            return HttpResponseRedirect(reverse("manage_sub_type"))
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(reverse("manage_sub_type"))


# manage Employee


def manageEmployeeView(request):  # sourcery skip: extract-method, last-if-guard
    if request.method == "POST":
        try:
            name = request.POST.get("name", "").strip()
            email = request.POST.get("email", "").strip()
            department_id = request.POST.get("department_id", "").strip()
            password = request.POST.get("password", "").strip()
            if not all([name, email, department_id, password]):
                messages.error(request, "Required all fileds")
                return HttpResponseRedirect(reverse("manage_employees"))
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                messages.error(request, "Invalid email format")
                return HttpResponseRedirect(reverse("manage_employees"))
            if Auth.objects.filter(email=email).exists():
                messages.error(request, f"Email {email} exists")
                return HttpResponseRedirect(reverse("manage_employees"))
            with transaction.atomic():
                department = Department.objects.get(id=department_id)
                user = Auth.objects.create_user(
                    name=name,
                    email=email,
                    password=password,
                    user_type="Employee",
                    is_active=True,
                )
                user.employee.department = department
                user.save()
                messages.success(request, f"Employee {name} created successfully")
                return HttpResponseRedirect(reverse("manage_employees"))
        except Exception as e:
            messages.error(request, f"Server Error: {e}")
            return HttpResponseRedirect(reverse("manage_employees"))
    else:
        f = Q()
        ob_list = [
            "auth__name",
            "created_at",
            "auth__email",
            "department__name" "-created_at",
            "-auth__name",
            "-auth__email",
            "department__name",
        ]
        order_by = request.GET.get("order_by", None)
        if not order_by or order_by not in ob_list:
            order_by = "auth__name"
        if query := request.GET.get("query", ""):
            f &= Q(Q(auth__name__icontains=query) | Q(auth__email__icontains=query))
        if department := request.GET.get("department", ""):
            f &= Q(department__name=department)
        employee_list = (
            Employee.objects.select_related("auth").filter(f).order_by(order_by)
        )
        page = request.GET.get("page", DEFAULT_PAGE)
        paginator = Paginator(employee_list, DEFAULT_PER_PAGE)
        try:
            employees = paginator.page(page)
        except PageNotAnInteger:
            employees = paginator.page(DEFAULT_PAGE)
        except EmptyPage:
            employees = paginator.page(paginator.num_pages)
        department_list = Department.objects.all().order_by("name")
        context = {
            "departments": department_list,
            "employees": employees,
            "query": query,
            "department": department,
            "order_by": order_by,
            "page": page,
        }
        return render(request, "AdminApp/manage_employee.html", context)


def updateEmployeeView(request):  # sourcery skip: extract-method, last-if-guard
    if request.method != "POST":
        messages.error(request, "Invalid Method")
        return HttpResponseRedirect(reverse("manage_employees"))
    try:
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        employee_id = request.POST.get("employee_id", "").strip()
        department_id = request.POST.get("department_id", "").strip()
        password = request.POST.get("password", "").strip()

        if not all([name, email, department_id, employee_id]):
            messages.error(request, "Required all fileds")
            return HttpResponseRedirect(reverse("manage_employees"))
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            messages.error(request, "Invalid email format")
            return HttpResponseRedirect(reverse("manage_employees"))
        if Auth.objects.filter(email=email).exclude(email=email).exists():
            messages.error(request, f"Email {email} exists")
            return HttpResponseRedirect(reverse("manage_employees"))
        with transaction.atomic():
            department = Department.objects.get(id=department_id)
            user = Employee.objects.get(id=employee_id).auth
            user.employee.department = department
            user.name = name
            user.email = email
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, f"Employee {name} updated successfully")
            return HttpResponseRedirect(reverse("manage_employees"))
    except Exception as e:
        messages.error(request, f"Server Error: {e}")
        return HttpResponseRedirect(reverse("manage_employees"))
