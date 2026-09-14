from __future__ import print_function
from werkzeug.datastructures import MultiDict, ImmutableMultiDict
import colorama

def dict_dump(passed_dict):
    if isinstance(passed_dict, (MultiDict,ImmutableMultiDict)):
        passed_dict = passed_dict.items(multi=True)

    for key, value in passed_dict:
        print(f"{colorama.Fore.CYAN}{key}: {colorama.Fore.YELLOW}{value}{colorama.Style.RESET_ALL}")

def request_dump(request, raw_body=None):
    colorama.init()

    if request.args:
        print(f"{colorama.Fore.MAGENTA}Arguments:{colorama.Style.RESET_ALL}")
        dict_dump(request.args)

    if request.form:
        print(f"{colorama.Fore.MAGENTA}Form items:{colorama.Style.RESET_ALL}")
        dict_dump(request.form)

    print(f"{colorama.Fore.MAGENTA}Headers:{colorama.Style.RESET_ALL}")
    dict_dump(request.headers)

    print(f"{colorama.Fore.MAGENTA}Raw Body:{colorama.Style.RESET_ALL}")
    if raw_body:
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode("utf-8",errors="replace")
        print(raw_body)
    else:
        print("(empty)")
