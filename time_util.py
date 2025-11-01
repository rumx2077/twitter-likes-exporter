import logging
from datetime import datetime, tzinfo
from enum import Enum
from functools import lru_cache
from typing import Optional, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

system_tz = datetime.now().astimezone().tzinfo


class DateTimeFormat(Enum):
    DISPLAY = "%Y-%m-%d %H:%M:%S %z"
    FILENAME = "%Y-%m-%d_%H-%M-%S_%z"
    TWITTER = "%a %b %d %H:%M:%S %z %Y"
    STANDARD = "%Y-%m-%d %H:%M:%S.%f"


@lru_cache(maxsize=128)
def _get_format_str(fmt: Union[DateTimeFormat, str]) -> str:
    return fmt.value if isinstance(fmt, DateTimeFormat) else fmt


@lru_cache(maxsize=128)
def get_tz(timezone_input: Union[str, tzinfo] = system_tz) -> tzinfo:
    if isinstance(timezone_input, tzinfo):
        return timezone_input
    try:
        return ZoneInfo(timezone_input)
    except Exception as e:
        logger.warning(f"{type(e).__name__}: {e}, using system timezone.")
        return system_tz


def format_datetime(
    dt: datetime,
    format: Union[DateTimeFormat, str] = DateTimeFormat.DISPLAY,
    default_tz: Union[str, tzinfo] = system_tz,
    target_tz: Optional[Union[str, tzinfo]] = None,
) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_tz(default_tz))
    if target_tz:
        dt = dt.astimezone(get_tz(target_tz))
    return dt.strftime(_get_format_str(format))


def parse_datetime(
    datetime_str: str,
    format: Optional[str] = None,
    default_tz: Union[str, tzinfo] = system_tz,
    target_tz: Optional[Union[str, tzinfo]] = None,
) -> datetime:
    # 将字符串解析为 datetime 对象。
    
    # 如果 format 为 None，则尝试 DateTimeFormat 中的所有格式。
    if format is None:
        for fmt in DateTimeFormat:
            try:
                dt = datetime.strptime(datetime_str, fmt.value)
                break
            except ValueError:
                pass
        else:
            raise ValueError(
                f"time string '{datetime_str}' does not match any known format"
            )
    else:
        dt = datetime.strptime(datetime_str, _get_format_str(format))
        

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_tz(default_tz))

    if target_tz:
        dt = dt.astimezone(get_tz(target_tz))

    return dt


def convert_datetime_format(
    datetime_str: str,
    from_format: Optional[str] = None,
    to_format: Union[DateTimeFormat, str] = DateTimeFormat.DISPLAY,
    default_tz: Union[str, tzinfo] = system_tz,
    target_tz: Optional[Union[str, tzinfo]] = None,
) -> str:
    dt = parse_datetime(
        datetime_str,
        from_format,
        default_tz=default_tz,
        target_tz=target_tz,
    )
    return format_datetime(dt, to_format)


def strfnow(
    tz: Union[str, tzinfo] = system_tz,
    format: Union[DateTimeFormat, str] = DateTimeFormat.DISPLAY
) -> str:
    return format_datetime(datetime.now(get_tz(tz)), format)


if __name__ == "__main__":
    # Set up logging for tests
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print("=== DateTime Utility Tests ===\n")

    # Test 1: Test _get_format_str
    print("1. Testing _get_format_str:")
    print(f"   DateTimeFormat.DISPLAY: {_get_format_str(DateTimeFormat.DISPLAY)}")
    print(f"   Custom string format: {_get_format_str('%Y-%m-%d')}")
    print()

    # Test 2: Test get_timezone
    print("2. Testing get_timezone:")
    print(f"   System timezone: {get_tz()}")
    print(f"   UTC timezone: {get_tz('UTC')}")
    print(f"   Asia/Shanghai: {get_tz('Asia/Shanghai')}")
    print(f"   America/New_York: {get_tz('America/New_York')}")
    print(f"   Invalid timezone: {get_tz('Invalid/Timezone')}")
    print(f"   Pass tzinfo object: {get_tz(ZoneInfo('UTC'))}")
    print()

    # Test 3: Test format_datetime
    print("3. Testing format_datetime:")
    now = datetime.now()
    now_with_tz = datetime.now(ZoneInfo('UTC'))

    print(f"   Current time (local): {now}")
    print(f"   Formatted (DISPLAY): {format_datetime(now)}")
    print(f"   Formatted (FILENAME): {format_datetime(now, DateTimeFormat.FILENAME)}")
    print(f"   Formatted (TWITTER): {format_datetime(now, DateTimeFormat.TWITTER)}")
    print(f"   Formatted (custom): {format_datetime(now, '%Y-%m-%d')}")
    print(
        f"   UTC time to Asia/Shanghai: {format_datetime(now_with_tz, target_tz='Asia/Shanghai')}"
    )

    # Test formatting a naive datetime with explicit default and target timezones
    naive_dt = datetime(2024, 1, 15, 10, 0, 0)
    print(
        f"   Naive dt '{naive_dt}' formatted (default=UTC, target=Shanghai): {format_datetime(naive_dt, default_tz='UTC', target_tz='Asia/Shanghai')}"
    )
    print(
        f"   Naive dt '{naive_dt}' formatted (default=system, target=NY): {format_datetime(naive_dt, target_tz='America/New_York')}"
    )
    print()

    # Test 4: Test parse_datetime
    print("4. Testing parse_datetime:")
    test_strings = [
        ("2024-01-15 14:30:00 +0800", DateTimeFormat.DISPLAY),
        ("2024-01-15_14-30-00_+0800", DateTimeFormat.FILENAME),
        ("Mon Jan 15 14:30:00 +0800 2024", DateTimeFormat.TWITTER),
    ]

    for test_str, fmt in test_strings:
        try:
            parsed = parse_datetime(test_str, fmt)
            print(f"   Parsed '{test_str}': {parsed}")
        except Exception as e:
            print(f"   Error parsing '{test_str}': {e}")

    # Test parsing with new timezone parameters
    naive_str = "2024-01-15 14:30:00"

    # Case 4.1: Localize a naive string using default_timezone
    parsed_naive = parse_datetime(
        naive_str, "%Y-%m-%d %H:%M:%S", default_tz="UTC"
    )
    print(f"   Parsed naive '{naive_str}' with default_timezone='UTC': {parsed_naive}")

    # Case 4.2: Localize a naive string and then convert it
    parsed_naive_converted = parse_datetime(
        naive_str,
        "%Y-%m-%d %H:%M:%S",
        default_tz="Asia/Shanghai",
        target_tz="America/New_York",
    )
    print(
        f"   Parsed naive '{naive_str}' (default=Shanghai) and converted to New York: {parsed_naive_converted}"
    )

    # Case 4.3: Convert an aware string
    aware_str = "2024-01-15 14:30:00 +0800"
    parsed_aware_converted = parse_datetime(
        aware_str, DateTimeFormat.DISPLAY, target_tz="America/New_York"
    )
    print(f"   Converted aware '{aware_str}' to New York: {parsed_aware_converted}")
    print()

    # Test 5: Test convert_datetime_format
    print("5. Testing convert_datetime_format:")
    twitter_str = "Mon Jan 15 14:30:00 +0800 2024"

    # Convert Twitter format to Display format
    converted = convert_datetime_format(
        twitter_str, DateTimeFormat.TWITTER, DateTimeFormat.DISPLAY
    )
    print(f"   Twitter to Display: '{twitter_str}' -> '{converted}'")

    # Convert Display format to Filename format
    display_str = "2024-01-15 14:30:00 +0800"
    converted = convert_datetime_format(
        display_str, DateTimeFormat.DISPLAY, DateTimeFormat.FILENAME
    )
    print(f"   Display to Filename: '{display_str}' -> '{converted}'")

    # Test with timezone conversion
    converted_aware = convert_datetime_format(
        display_str, DateTimeFormat.DISPLAY, target_tz="America/New_York"
    )
    print(
        f"   Convert aware string with timezone conversion: '{display_str}' -> '{converted_aware}'"
    )

    # Test with naive string and both timezones
    converted_naive = convert_datetime_format(
        naive_str,
        "%Y-%m-%d %H:%M:%S",
        DateTimeFormat.DISPLAY,
        default_tz="Asia/Shanghai",
        target_tz="America/New_York",
    )
    print(
        f"   Convert naive string (default=Shanghai, target=New York): '{naive_str}' -> '{converted_naive}'"
    )

    # Test error handling
    print("   Testing error handling:")
    try:
        invalid_str = "invalid datetime string"
        convert_datetime_format(
            invalid_str, DateTimeFormat.DISPLAY, DateTimeFormat.FILENAME
        )
    except ValueError as e:
        print(f"   Successfully caught expected error for '{invalid_str}': {e}")

    # Test 6: Cache functionality
    print("6. Testing cache functionality:")
    # Clear cache first
    _get_format_str.cache_clear()
    get_tz.cache_clear()

    print(f"   Cache info for _get_format_str before: {_get_format_str.cache_info()}")
    print(f"   Cache info for get_timezone before: {get_tz.cache_info()}")

    # Make some calls
    for _ in range(3):
        _get_format_str(DateTimeFormat.DISPLAY)
        _get_format_str("%Y-%m-%d")
        get_tz("UTC")
        get_tz("Asia/Shanghai")

    print(f"   Cache info for _get_format_str after: {_get_format_str.cache_info()}")
    print(f"   Cache info for get_timezone after: {get_tz.cache_info()}")
    print()

    # Test 7: Edge cases
    print("7. Testing edge cases:")

    # Test with local timezone
    dt = datetime.now()
    formatted = format_datetime(dt, DateTimeFormat.DISPLAY)
    print(f"   Format with local timezone: {formatted}")

    # Test with very old date
    old_date = datetime(1900, 1, 1, 12, 0, 0)
    formatted = format_datetime(old_date, DateTimeFormat.DISPLAY)
    print(f"   Format old date (1900-01-01): {formatted}")

    # Test with future date
    future_date = datetime(2099, 12, 31, 23, 59, 59)
    formatted = format_datetime(future_date, DateTimeFormat.DISPLAY)
    print(f"   Format future date (2099-12-31): {formatted}")

    print("\n=== All tests completed ===")
