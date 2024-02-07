import sys
import dotenv
from signal import signal, SIGINT

from util import EVE_HTTP
from util import EVE_SSH
from util import EVE_INFO

from util import init_args
from util import handler
from util import init_server_info
from util import args_check


if __name__ == "__main__":
    dotenv.load_dotenv()
    eve_info = EVE_INFO()

    init_server_info(eve_info)

    signal(SIGINT, handler)
    args = init_args().parse_args()

    # login to eve api server as admin
    eve_http = EVE_HTTP(eve_url=eve_info.url, http_user=eve_info.http_user, http_password=eve_info.http_pass)

    args_check(args, eve_http)


#  ssh connect to eve-ng
    eve_ssh = EVE_SSH(ip=eve_info.ip, user=eve_info.server_user, password=eve_info.server_pass)
    eve_ssh.connect()


    print("[    Info  ] ==> Insert Information for Node A")
    node, node_intf, _ = eve_http.select_node_interface(device="A")
    # check if interface is connected
    if node_intf["connected"] == "False":
        print(f"[    Error ] ==> selected Interface {node_intf['name']} on device {node['name']} is not connected.")
        sys.exit(1)
    linux_intf = f"vunl{eve_http.user_id}_{node['id']}_{node_intf['id']}"

    # get network_id
    for item in eve_http.lab_networks:
        if item == node_intf["network_id"]:
            network_id = item
            network = eve_http.lab_networks[item]

    bridge_name = f"vnet{ eve_http.user_id }_{network_id}"

    print(f"[    Info  ] ==> Bridge name on Linux = {bridge_name}")


    # read lab file
    lab_file = eve_ssh.get_lab_file(lab_info=eve_http.lab)

    if "networks" in lab_file["lab"]["topology"]:
        lab_networks = lab_file["lab"]["topology"]["networks"]
    else:
        lab_file["lab"]["topology"]["networks"] = {}
        lab_networks = lab_file["lab"]["topology"]["networks"]
    lab_nodes = lab_file["lab"]["topology"]["nodes"]

    
    for node in lab_nodes["node"]:
        if node.get("interface", None):
            if isinstance(node["interface"], list):
                node["interface"] =  list(filter(lambda x: int(x["@network_id"]) != int(network_id), node["interface"]))
            elif isinstance(node["interface"], dict):
                if int(node["interface"]["@network_id"]) == int(network_id):
                    node.pop("interface")

    if str(network["visibility"]) == "0":
        if isinstance(lab_networks["network"], dict):
            lab_networks["network"] = []
        elif isinstance(lab_networks["network"], list):
            lab_networks["network"] = list(filter(lambda x: int(x["@id"]) != int(network_id), lab_networks["network"]))

    print("[    Info  ] ==> Update lab file")
    eve_ssh.update_lab_file(lab_info=eve_http.lab, file_data=lab_file)

    print("[    Info  ] ==> delete bridge interface")
    if str(network["visibility"]) == "0":
        eve_ssh.send_command(f"ip link del {bridge_name}")
    else:
        eve_ssh.send_command(f"ip link set dev {linux_intf} nomaster")

    print("[    Info  ] ==> Close SSH connection")
    eve_ssh.client.close()
    print("[    Info  ] ==> Close HTTP connection")
    eve_http.session.close()

