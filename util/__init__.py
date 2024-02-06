import os
from .util import *
from dotenv import load_dotenv
from dataclasses import dataclass

@dataclass
class EVE_INFO():
    ip: str = ""
    server_user: str = ""
    server_pass: str = ""
    http_user: str = ""
    http_pass: str = ""
    url: str = ""


def init_server_info(eve_info: EVE_INFO):
    eve_info.ip = os.environ.get("eve_server_ip")
    eve_info.server_user = os.environ.get("eve_server_user")
    eve_info.server_pass= os.environ.get("eve_server_password")
    eve_info.http_user = os.environ.get("http_user")
    eve_info.http_pass = os.environ.get("http_password")
    eve_info.url = f"http://{eve_info.ip}/api"

def args_check(args, eve_http: EVE_HTTP):

    if response:= eve_http.connect() != True:
        print("[    Error ] ==> could not connect to EVE http server.")
        print(response.text)
        sys.exit(1)

    eve_http.get_lab_lists()
    # show all labs using -L
    if args.lab_list:
        show_table({"List of Labs": eve_http.lab_lists})
        sys.exit(0)

    # show all users using -U
    if args.users_list:
        eve_users = eve_http.get_users()
        show_table({"Users List": eve_users})
        sys.exit()

    if args.current_lab:
        eve_http.lab_name = args.current_lab
    else:
        eve_http.lab_name = input("Please insert lab id: ")

    # find lab in question
    if current_lab := eve_http.find_lab_name():
        pass
    else:
        print(f"[    Error ] ==> Lab {eve_http.lab_name} is not exist.")
        sys.exit(1)

    # get all nodes in current lab
    eve_http.get_lab_nodes()

    # get list of lab networks

    eve_http.get_lab_networks()

#     # show all all nodes table
    if not eve_http.lab_nodes:
        print("[    Info  ] ==> there is no node in the LAB")
        sys.exit(1)
    
    if args.all_nodes:
        show_table({"Nodes List": eve_http.lab_nodes})
        sys.exit(0)


    if args.node_id:
        if node:= eve_http.is_node_id(args.node_id):
            if node["status"] == "passive":
                print("[    Warrning ] ==> cannot print list of interfaces for Bridge and cloud node")
                sys.exit()
            else:
                node_interfaces = eve_http.get_node_interfaces(node)
                show_table({f"List of interfaces for {node['name']}": node_interfaces})
                sys.exit()
        else:
            print("[    Error ] ==> Selected Node ID is not exists in the lab")
            sys.exit(1)
