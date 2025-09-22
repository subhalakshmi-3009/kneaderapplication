# kneader/time_utils.py

class TimeUtils:

    @staticmethod
    async def to_seconds(timestamp: str) -> int:
        """Convert HH.MM.SS string → total seconds"""
        hh, mm, ss = map(int, timestamp.split('.'))
        return hh * 3600 + mm * 60 + ss

    @staticmethod
    async def to_hh_mm_ss(seconds: int) -> str:
        """Convert seconds → HH.MM.SS string"""
        sign = '-' if seconds < 0 else ''
        seconds = abs(seconds)
        hh = seconds // 3600
        remaining_seconds = seconds % 3600
        mm = remaining_seconds // 60
        ss = remaining_seconds % 60
        return f"{sign}{hh:02d}.{mm:02d}.{ss:02d}"

    @staticmethod
    async def time_difference_seconds(time1: str, time2: str) -> int:
        """Return difference (in seconds) between two HH.MM.SS times"""
        time1_seconds = await TimeUtils.to_seconds(time1)
        time2_seconds = await TimeUtils.to_seconds(time2)
        return time1_seconds - time2_seconds

    @staticmethod
    async def time_difference(time1: str, time2: str) -> str:
        """Return difference (in HH.MM.SS format) between two times"""
        time1_seconds = await TimeUtils.to_seconds(time1)
        time2_seconds = await TimeUtils.to_seconds(time2)
        difference_seconds = time1_seconds - time2_seconds
        return await TimeUtils.to_hh_mm_ss(difference_seconds)
