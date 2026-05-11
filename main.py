import network
import socket
import time
from machine import Pin

# ===== WiFi credentials =====
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"

# ===== GPIO setup =====
GPIO_PINS = {
    1: Pin(1, Pin.OUT),
    2: Pin(2, Pin.OUT),
    3: Pin(3, Pin.OUT),
    4: Pin(4, Pin.OUT),
}

for pin in GPIO_PINS.values():
    pin.value(0)


def connect_wifi(ssid, password, timeout=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("WiFi already connected:", wlan.ifconfig())
        return wlan

    print("Connecting to WiFi:", ssid)
    wlan.connect(ssid, password)

    start = time.time()
    while not wlan.isconnected() and (time.time() - start) < timeout:
        print("Waiting for WiFi...")
        time.sleep(1)

    if wlan.isconnected():
        print("WiFi connected:", wlan.ifconfig())
    else:
        print("WiFi connection timeout")

    return wlan


def load_index_html(path="index.html"):
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError:
        return "<html><body><h1>CORE_OS</h1><p>index.html not found.</p></body></html>"


def gpio_states_json():
    # Compact JSON builder to avoid extra imports.
    parts = []
    for gpio_num in (1, 2, 3, 4):
        state = GPIO_PINS[gpio_num].value()
        parts.append('"%d":%d' % (gpio_num, state))
    return "{" + ",".join(parts) + "}"


def build_http_response(body, status="200 OK", content_type="text/html"):
    return (
        "HTTP/1.1 %s\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n"
        "\r\n"
        "%s"
    ) % (status, content_type, len(body), body)


def handle_request(request_path, html_cache):
    if request_path == "/" or request_path == "/index.html":
        return build_http_response(html_cache, "200 OK", "text/html")

    if request_path == "/states":
        return build_http_response(gpio_states_json(), "200 OK", "application/json")

    if request_path.startswith("/gpio/"):
        try:
            gpio_num = int(request_path.split("/")[2])
        except (IndexError, ValueError):
            return build_http_response("Invalid GPIO", "400 Bad Request", "text/plain")

        if gpio_num in GPIO_PINS:
            pin = GPIO_PINS[gpio_num]
            pin.value(0 if pin.value() else 1)
            body = '{"gpio":%d,"state":%d}' % (gpio_num, pin.value())
            return build_http_response(body, "200 OK", "application/json")

        return build_http_response("GPIO not supported", "404 Not Found", "text/plain")

    return build_http_response("Not Found", "404 Not Found", "text/plain")


def close_socket_safe(sock_obj):
    if sock_obj is not None:
        try:
            sock_obj.close()
        except OSError:
            pass


def start_server():
    html_cache = load_index_html()
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]

    server_sock = None
    try:
        server_sock = socket.socket()
        # Reuse address to reduce EADDRINUSE risk after restart.
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(addr)
        server_sock.listen(4)
        print("HTTP server running on port 80")

        while True:
            client_sock = None
            try:
                client_sock, client_addr = server_sock.accept()
                request = client_sock.recv(1024)
                if not request:
                    continue

                request_line = request.decode("utf-8", "ignore").split("\r\n")[0]
                parts = request_line.split(" ")
                if len(parts) < 2:
                    response = build_http_response("Bad Request", "400 Bad Request", "text/plain")
                else:
                    path = parts[1]
                    print("%s -> %s" % (client_addr[0], path))
                    response = handle_request(path, html_cache)

                client_sock.send(response)

            except OSError as err:
                print("Client error:", err)
            finally:
                close_socket_safe(client_sock)

    except OSError as err:
        print("Server error:", err)
    finally:
        close_socket_safe(server_sock)


if __name__ == "__main__":
    wlan = connect_wifi(SSID, PASSWORD)
    if wlan.isconnected():
        start_server()
    else:
        print("Server not started because WiFi is disconnected.")
