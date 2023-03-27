# GroupChatRoomApp-socket-programming
- Name: Ouqi Lin
- UNI: ol2251

## How to Use

### Start the App
Input the below command in command line interface, a server/client will start. You can run one server and multiple clients on one machine. 

#### Server
```python
python3 ChatApp.py -s <server-listen-port>
# example:
python3 ChatApp.py -s 6666
```

#### Client

```python
python3 ChatApp.py -c <client-name> <server-ip> <server-listen-port> <client-listen-port>
# example:
python3 ChatApp.py -c X localhost 6666 7771
```
Note: `;` is not allowed in client name.

### Functions of Client

#### De-registration
Client can deregistrate itself by either method
1.  type in the below command in CLI:
    ```python
    dereg <client-name>
    ```
2.  press `CTRL+C`
3.  close the CLI window  

Note: Client can only dereg itself.

#### Private Chatting
Client can send direct message to another client.
```python
send <receiver-client-name> <message>
```

#### Create A Group
Client can create a group chat room.
```python
create_group <group-name>
```
Note: `;` is not allowed in group name.

#### List Existing Groups
Client can know all available groups before joining.
```python
list_groups
```

#### Join A Group
Client can join into an existing group. Client can only be in one group at a time. When in group, client cannot send private message, but can receive private message.
```python
join_group <group-name>
```

#### Chat in the Group
Client can send group messages to all other clients in the same group.
```python
send_group <group message>
```

#### List Group Members
Client can know the group members of the group it's in.
```python
list_members
```

#### Leave the Group
Client can leave the current group.
```python
leave_group
```

## Program Design
### Server Components
- threads
  - main thread `serverMode()`:  
    keep listening to all kinds of incoming client command requests, and clients' ack reply of group messages.
  - sub threads : 
    - `serverRespond()`: each time server need to respond (e.g. broadcast table, send ack,...), create a sub-thread
    - `sleep_and_wait_for_acks()`: Server needs to receive acks from group members. After server finished sening out a group message, a sub-thread will start. It will first sleep for 500msec, then wake up to check if required acks are received. 
- sockets
  - listening socket:  
    is used in main thread `serverMode()`
  - sending socket:  
    is used in each sub-thread `serverRespond()` and in main thread `serverMode()` when broadcasting group messages.
    
- major variables
  - `client_table`:  
    maintain client information (name, IP, port number, online status)
  - `group_table`:  
    maintain group information (name, members set)
  - `ack_dict`:  
    record acknowledgement requirements of group members, for each group message which is uniquely indentified by (`sender_name`, `message timestamp`)
- locks
    - `send_lock`:  
        will take effects each time `server_send_socket` is used.
    - `group_lock`:  
        will take effects each time `group_table` is read or written (e.g. create new groups, add new members, remove nonresponsive members).
    - `ack_lock`:  
        will take effects when new ack requirements are added, modified and deleted.

### Client Components
- threads
  - keyboard thread (main thread) `clientMode()`: 
    1. continue taking user inputs
    1. verify user input is a valid command
    1. structure the sending-out packet format
    1. use `client_send_socket` to send packet to server or another client, wait 500msec for ack, retry for 5 times
    1. based on server or another client's ack and additional information, perform corresponding actions
  - listening thread `clientListen()`: start before keyboard thread, sitting aside main thread, listening to all kinds of incoming messages
    - acknowledgements
    - client table broadcasted from server
    - group message broadcasted from server
    - private message sent from another client
- sockets
  - sending socket:  
    is used in the keyboard thread `clientMode()`, and listening thread `clientListen()` when need to reply ack for group messages and private messages
  - listening socket:  
    is used in the listening thread `clientListen()`
- major variables
  - `client_table`:  
    maintain client information (name, IP, port number, online status)
  - `ack_dict`:  
    record acknowledgement requirements of server and all clients, default `False`; if received ack, change to `True`
  - `pri_msg_queue`:  
    when client in group mode, the private messages it received will be kept in `pri_msg_queue`
- locks
    - `send_lock`:  
        will take effects each time `client_send_socket` is used.
    - `ack_lock`:  
        will take effects when keyboard thread is trying to read, and when listening thread is trying to write.
  
### Diagram
<img src="client.jpg">
<img src="server.jpg">

### Packet Format
All packets will be wrapped in a uniform formats, including client requests, ack response, broadcast tables, etc.
```
sender_listening_port:
<sender_listening_port>
sender_name:
<sender_name>
msg_type:
<reg_ack/ack/table/grp_msg/pri_msg> (client may receive)
<reg/dereg/create_group/list_groups/join_group/leave_group/list_members/send_group/ack/kick> (server may receive)
message:
<actual message>
```

- `sender_name`:  
    uniquely identify an instance, is used as a unique user id in this implementation. Server's "sender_name" is "server". Client's "sender_name" is the name provided when register. Therefore, I disallow duplicate name for client registration.
- `msg_type`:
    In order to identify the packet content sending between instances and direct to the corresponding actions, I use this `msg_type` field as part of the packet header.  
    - Client may receive: `reg_ack` registration request acknowledgement; `ack` from server and other clients; `table` client_table broadcasted from server; `grp_msg` group message broadcasted from server; `pri_msg` private message sent from another client.
    - Server may receive: `reg/dereg/create_group/list_groups/join_group/leave_group/list_members/send_group` corresponding to every client function. `ack` from group members receiving group messages. `kick` when client A find client B not responding to A's message, A will notify server to change B's status to offline.

### Known Bugs


## Test Cases
