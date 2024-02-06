## EVE-NG Community Hot Connection Script
In the EVE-NG Community version, we encounter a limitation where running nodes cannot be directly connected together. Instead, we must power down the nodes before being able to establish connections between them.

This has been a persistent issue for me, particularly when working with resource-intensive images like IOS XR, as it significantly delays the workflow to power them down and then wait for them to boot up again.

After encountering this challenge numerous times, I embarked on finding a solution to streamline the process of connecting running nodes. Initially, manual intervention was required, which proved to be time-consuming and cumbersome. Consequently, I developed a Python script to automate the "hot" connection process, eliminating the need for manual intervention and saving valuable time.


## how to install
- step 1:
    clone the repo using
    ```
    git clone 
    ```
- step 2
    install requirment packages
    ```
    pip install -r .\requirements.txt
    ```
- step 3
    edit .env file and add your eve server information.Script need have ssh access and http access to server.
    ```
    # eve-ng server ip address.
    eve_server_ip="192.168.0.10"
    # eve-ng server login detaild
    eve_server_user="root"
    eve_server_password="eve"
    # eve-ng html login detail
    http_user="admin"
    http_password="eve"
    ```
- step 4
    you can run the script using below argument
    -L shows list of all labs
    -U shows list of all users
    -C { lab name or lab id } current lab name or ID the you would like to work on
    -A shows list of all nodes in the lab
    -N { node_id } shows all interfaces for a node id
    ```
        python add_link.py -L # shows list of all labs
        python add_link.py -U # shows list of all users
        python add_link.py -C 2c940253- -A # show list of all nodes in a lab you need to provide lab name or ID as argument
        python add_link.py -C 2c940253- -N 1 # shows list all interfaces for a node
        python add_link.py -C 2c940253- # script will ask user to give node_a and node_b details and it will connect them toghther

        python remove_link.py -L # shows list of all labs
        python remove_link.py -U # shows list of all users
        python remove_link.py -C 2c940253- -A # show list of all nodes in a lab you need to provide lab name or ID as argument
        python remove_link.py -C 2c940253- -N 1 # shows list all interfaces for a node
        python remove_link.py -C 2c940253- # script will ask user to give node details and it will remove the connection from both end
    ```


## Problems and Suggestions:
If you encounter any issues while using the script or have suggestions for improvement, please don't hesitate to reach out. Your feedback is invaluable in enhancing the functionality and efficiency of the script. Feel free to share any problems you encounter or ideas for enhancements, and together, we can continue refining and improving the script.


