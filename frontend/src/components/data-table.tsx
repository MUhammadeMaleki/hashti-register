import type { ReactNode } from "react";

export type Column<T> = { key: string; title: string; render: (row: T) => ReactNode };

export function DataTable<T>({ columns, rows, empty }: {
  columns: Column<T>[]; rows: T[]; empty: string;
}) {
  return <div className="table-scroll"><table><thead><tr>
    {columns.map((column) => <th scope="col" key={column.key}>{column.title}</th>)}
  </tr></thead><tbody>
    {rows.length === 0 ? <tr><td colSpan={columns.length}>{empty}</td></tr> :
      rows.map((row, index) => <tr key={index}>{columns.map((column) =>
        <td key={column.key}>{column.render(row)}</td>)}</tr>)}
  </tbody></table></div>;
}
