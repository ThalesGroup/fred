
/**
 * Aligns a start and end date to the given precision.
 * For example, with "hour" precision, the start is rounded down to the start of the hour,
 * and the end is rounded up to the end of the hour (inclusive).
 */
import dayjs, { Dayjs, OpUnitType } from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(utc);
dayjs.extend(timezone);

const precisionToUnit: Record<"sec" | "min" | "hour" | "day", OpUnitType> = {
  sec: "second",
  min: "minute",
  hour: "hour",
  day: "day",
};

export function alignDateRangeToPrecision(
  start: Dayjs,
  end: Dayjs,
  precision: "sec" | "min" | "hour" | "day"
): [string, string] {
  const unit = precisionToUnit[precision];
  const alignedStart = dayjs.utc(start).startOf(unit);
  const alignedEnd = dayjs.utc(end).endOf(unit);
  return [alignedStart.toISOString(), alignedEnd.toISOString()];
}
