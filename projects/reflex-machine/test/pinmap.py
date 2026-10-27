"""Cross-check: firmware pins  <->  PCB netlist  <->  board nets.

Reads the pin numbers straight out of the two .cpp files and compares them with gen/netlist.py,
so a wiring/firmware mismatch cannot slip through silently.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PRJ, "gen"))
import netlist as NL  # noqa: E402

MEGA_SRC = os.path.join(os.path.dirname(os.path.dirname(PRJ)), "CODES", "arduino_main_code.cpp")
ESP_SRC = os.path.join(os.path.dirname(os.path.dirname(PRJ)), "CODES", "ESP32_main_code.cpp")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def firmware_pins():
    src = read(MEGA_SRC)
    pins = {}
    m = re.search(r"PWM_PINS\[\d+\]\s*=\s*\{([^}]*)\}", src)
    for i, num in enumerate(n.strip() for n in m.group(1).split(",")):
        pins["MAG%d_PWM" % (i + 1)] = "D" + num
    for name, net in (("BTN_SPEED1", "BTN_S1"), ("BTN_SPEED2", "BTN_S2"), ("BTN_SPEED3", "BTN_S3"),
                      ("BTN_RESET", "BTN_RST"), ("COIN_PIN", "COIN_IN")):
        pins[net] = "D" + re.search(r"#define\s+%s\s+(\d+)" % name, src).group(1)
    for name, net in (("SEG_DATA", "SEG_DATA"), ("SEG_LATCH", "SEG_LATCH"), ("SEG_CLOCK", "SEG_CLOCK")):
        pins[net] = re.search(r"#define\s+%s\s+(A\d)" % name, src).group(1)
    for k in range(1, 5):
        pins["LED%d" % k] = re.search(r"const int LED%d\s*=\s*(A\d)" % k, src).group(1)
    pins["MEGA_TX1"] = "D18"      # Serial1 on the Mega is fixed in hardware
    pins["ESP_TX2"] = "D19"
    esp = read(ESP_SRC)
    esp_pins = {"ESP_RX2": int(re.search(r"#define\s+RX2_PIN\s+(\d+)", esp).group(1)),
                "ESP_TX2": int(re.search(r"#define\s+TX2_PIN\s+(\d+)", esp).group(1))}
    return pins, esp_pins


def board_pins():
    mega = next(p for p in NL.PARTS if p["ref"] == "A1")
    esp = next(p for p in NL.PARTS if p["ref"] == "A2")
    return ({net: pad for pad, net in mega["pins"].items()},
            {net: pad for pad, net in esp["pins"].items()})


ESP_PAD_TO_GPIO = {"25": 16, "24": 17, "6": 32, "7": 33, "8": 25, "9": 26, "10": 27, "11": 14}


def main():
    fw, fw_esp = firmware_pins()
    board, board_esp = board_pins()
    rows, bad = [], 0
    for net in sorted(fw, key=lambda n: (n.split("_")[0], n)):
        want, got = fw[net], board.get(net, "-- missing --")
        ok = want == got
        bad += not ok
        rows.append("%-12s firmware %-5s board %-12s %s" % (net, want, got, "OK" if ok else "<-- MISMATCH"))
    for net, gpio in fw_esp.items():
        pad = board_esp.get(net)
        got = ESP_PAD_TO_GPIO.get(pad)
        ok = got == gpio
        bad += not ok
        rows.append("%-12s firmware GPIO%-2s board pin %-3s (GPIO%s) %s"
                    % (net, gpio, pad, got, "OK" if ok else "<-- MISMATCH"))
    print("\n".join(rows))
    print("\n%d signals checked, %d mismatches" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
