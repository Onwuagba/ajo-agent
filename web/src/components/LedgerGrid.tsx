import { useMemo, useRef } from "react";
import { AllCommunityModule, ModuleRegistry, themeQuartz } from "ag-grid-community";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { memberById } from "../data/roster";
import type { LedgerRow } from "../data/types";
import { set } from "../state/store";
import { Avatar, Chip, KindIcon, StatusChip, dateTime, kindLabel, money } from "./ui";

ModuleRegistry.registerModules([AllCommunityModule]);

const theme = themeQuartz.withParams({
  backgroundColor: "var(--surface)", foregroundColor: "var(--ink)", headerBackgroundColor: "var(--surface2)", headerTextColor: "var(--ink2)", borderColor: "var(--line)",
  oddRowBackgroundColor: "transparent", rowHoverColor: "color-mix(in srgb, var(--brand) 7%, transparent)", accentColor: "var(--brand)", fontFamily: "var(--font-body)", fontSize: 14,
  headerFontWeight: 700, rowHeight: 54, headerHeight: 46, wrapperBorderRadius: 14, spacing: 9, selectedRowBackgroundColor: "color-mix(in srgb, var(--brand) 12%, transparent)",
});

type Row = LedgerRow & { _flash: boolean };
const Who = (p: ICellRendererParams<Row>) => p.data ? <div className="cell-member"><Avatar id={p.data.member} size={28} /><span>{memberById(p.data.member).first}</span></div> : null;
const Kind = (p: ICellRendererParams<Row>) => p.data ? <div className="cell-member" style={{ gap: 7 }}><span style={{ display: "inline-flex", color: p.data.kind === "payout" ? "var(--warn)" : "var(--good)" }}><KindIcon k={p.data.kind} /></span>{kindLabel[p.data.kind]}</div> : null;
const Status = (p: ICellRendererParams<Row>) => p.data ? <div className="cell-member" style={{ gap: 6 }}><StatusChip s={p.data.status} />{p.data.simulated && <span className="chip sim">simulated</span>}</div> : null;
const Amount = (p: ICellRendererParams<Row>) => p.data ? <b className="num" style={{ color: p.data.kind === "payout" ? "var(--ink)" : "var(--good)" }}>{p.data.kind === "payout" ? "−" : "+"}{money(p.data.amount)}</b> : null;
const Mono = (p: ICellRendererParams<Row>) => <span className="mono faint">{p.value}</span>;
const Ver = (p: ICellRendererParams<Row>) => <Chip>v{p.value}</Chip>;

export function LedgerGrid({ rows, quick }: { rows: (LedgerRow & { _flash: boolean })[]; quick: string }) {
  const ref = useRef<AgGridReact<Row>>(null);
  const cols = useMemo<ColDef<Row>[]>(() => [
    { field: "ts", headerName: "When", width: 160, sort: "desc", valueFormatter: (p) => dateTime(p.value).replace(" UTC", ""), comparator: (a, b) => a - b },
    { field: "cycle", headerName: "Cycle", width: 96, cellRenderer: (p: ICellRendererParams<Row>) => <Chip>#{p.value}</Chip>, filter: "agNumberColumnFilter" },
    { field: "kind", headerName: "Type", width: 170, cellRenderer: Kind },
    { field: "member", headerName: "Member", width: 150, cellRenderer: Who, valueGetter: (p) => (p.data ? memberById(p.data.member).name : "") },
    { field: "amount", headerName: "Amount", width: 120, cellRenderer: Amount, type: "rightAligned" },
    { field: "status", headerName: "Status", width: 220, cellRenderer: Status },
    { field: "paypalId", headerName: "PayPal reference", width: 190, cellRenderer: Mono },
    { field: "ruleVersion", headerName: "Rules", width: 96, cellRenderer: Ver },
    { field: "rule", headerName: "Rule applied", flex: 1, minWidth: 260 },
  ], []);
  return (
    <div className="ag-wrap" role="region" aria-label="Shared ledger">
      <AgGridReact<Row> ref={ref} theme={theme} rowData={rows} columnDefs={cols} getRowId={(p) => p.data.id} quickFilterText={quick} animateRows
        defaultColDef={{ sortable: true, resizable: true, filter: true }} suppressCellFocus rowClassRules={{ "flash-row": (p) => !!p.data?._flash }}
        onRowClicked={(e) => e.data && set({ drawerRow: e.data.id })} rowSelection={undefined} overlayNoRowsTemplate="No rows match these filters" />
    </div>
  );
}
