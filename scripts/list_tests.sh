#!/bin/bash

echo "=== Available Tests in product_connect ==="
echo "========================================="

echo -e "\n🐍 Python Unit Tests:"
echo "----------------------------"
find addons/product_connect/tests -name "test_*.py" -exec grep -H "def test_" {} \; | while read -r line; do
    file=$(echo "$line" | cut -d: -f1 | sed 's/.*\///')
    test=$(echo "$line" | cut -d: -f2 | sed 's/def //' | sed 's/(.*$//')
    echo "  ✓ $file: $test"
done

echo -e "\n🌐 JavaScript Tests:"
echo "----------------------------"
find addons/product_connect/static/tests -name "*.test.js" -exec grep -H "test(" {} \; | while read -r line; do
    file=$(echo "$line" | cut -d: -f1 | sed 's/.*\///')
    test=$(echo "$line" | cut -d: -f2 | sed 's/.*test("//' | sed 's/".*//')
    echo "  ✓ $file: $test"
done

echo -e "\n🎭 Tour Tests:"
echo "----------------------------"
find addons/product_connect/static/tests/tours -name "*.js" -exec grep -H "web_tour.tours" {} \; | while read -r line; do
    file=$(echo "$line" | cut -d: -f1 | sed 's/.*\///')
    tour=$(echo "$line" | cut -d: -f2 | sed 's/.*add("//' | sed 's/".*//')
    echo "  ✓ $file: $tour"
done

echo -e "\n📊 Test Count Summary:"
echo "----------------------------"
python_tests=$(find addons/product_connect/tests -name "test_*.py" -exec grep -c "def test_" {} \; | awk '{sum+=$1} END {print sum}')
js_tests=$(find addons/product_connect/static/tests -name "*.test.js" -exec grep -c "test(" {} \; | awk '{sum+=$1} END {print sum}')
tour_tests=$(find addons/product_connect/static/tests/tours -name "*.js" -exec grep -c "web_tour.tours" {} \; | awk '{sum+=$1} END {print sum}')

echo "  Python Unit Tests: $python_tests"
echo "  JavaScript Tests: $js_tests"
echo "  Tour Tests: $tour_tests"
echo "  Total: $((python_tests + js_tests + tour_tests))"

echo -e "\n🚀 Usage:"
echo "----------------------------"
echo "  ./scripts/run_tests.sh python    # Run all Python tests"
echo "  ./scripts/run_tests.sh js        # Run JavaScript tests"
echo "  ./scripts/run_tests.sh tour      # Run tour tests"
echo "  ./scripts/run_tests.sh           # Run all tests"