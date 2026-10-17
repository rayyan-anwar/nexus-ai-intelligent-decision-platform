CXX      ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
BUILD    := build
UNAME    := $(shell uname -s)
ifeq ($(UNAME),Darwin)
LIB := $(BUILD)/libnexus_accel.dylib
else
LIB := $(BUILD)/libnexus_accel.so
endif

.PHONY: all test bench clean
all: $(LIB)

$(LIB): src/nexus_accel.cpp
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -fPIC -fvisibility=hidden -shared $< -o $@

$(BUILD)/test_accel: tests/test_accel.cpp src/nexus_accel.cpp
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -fsanitize=address,undefined tests/test_accel.cpp src/nexus_accel.cpp -o $@

test: $(BUILD)/test_accel
	./$(BUILD)/test_accel

bench: $(LIB)
	PYTHONPATH=../../backend python3 benchmarks/bench_accel.py

clean:
	rm -rf $(BUILD)
