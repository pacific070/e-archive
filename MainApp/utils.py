import uuid
import sys
import time


def getId(prefix: str = "") -> str:
    return f'{prefix}{uuid.uuid4().hex}'


def generate_ticket_no(cid: str = '0', company_name: str = '') -> str:
    if cid is None:
        return f'{company_name}00001'
    if len(cid) == 1:
        return f'{company_name}0000{cid}'
    elif len(cid) == 2:
        return f'{company_name}000{cid}'
    elif len(cid) == 3:
        return f'{company_name}00{cid}'
    elif len(cid) == 4:
        return f'{company_name}0{cid}'
    else:
        return f'{company_name}{cid}'


def Syserror(e):
    exception_type, exception_object, exception_traceback = sys.exc_info()
    filename = exception_traceback.tb_frame.f_code.co_filename
    line_number = exception_traceback.tb_lineno
    print("ERROR --> Mesaage: ", e)
    print("ERROR --> Exception type: ", exception_type)
    print("ERROR --> File name: ", filename)
    print("ERROR --> Line number: ", line_number)
    return None


def convert_hour(seconds):
    tm_obj = time.gmtime(seconds)
    if tm_obj.tm_hour > 0:
        if tm_obj.tm_min > 0:
            return f'{tm_obj.tm_hour}:{tm_obj.tm_min}'
        return f'{tm_obj.tm_hour}:0'
    else:
        return f'0:{tm_obj.tm_min}'
