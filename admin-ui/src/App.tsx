import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BadgeCheck,
  Building2,
  Check,
  FileText,
  Home,
  LifeBuoy,
  Lock,
  Scale,
  Search,
  Unlock,
  UserPlus,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

const menuItems = [
  { key: "dashboard", label: "Главная", icon: Home },
  { key: "registrations", label: "Регистрации", icon: UserPlus },
  { key: "verification", label: "Верификация", icon: BadgeCheck },
  { key: "access", label: "Доступ компаний", icon: Building2 },
  { key: "disputes", label: "Споры", icon: Scale },
  { key: "support", label: "Поддержка", icon: LifeBuoy },
  { key: "search", label: "Поиск / Реестр", icon: Search },
];

type DialogState = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  variant: "primary" | "danger";
};

const defaultDialog: DialogState = {
  open: false,
  title: "",
  description: "",
  confirmLabel: "Подтвердить",
  variant: "primary",
};

const statusBadge = (status: string) => {
  const normalized = status.toUpperCase();
  if (["ACTIVE", "APPROVED", "RESOLVED", "REVIEWED"].includes(normalized)) {
    return <Badge variant="success">{status}</Badge>;
  }
  if (["IN_REVIEW", "WAITING", "NEED_INFO", "WAITING_INFO"].includes(normalized)) {
    return <Badge variant="warning">{status}</Badge>;
  }
  if (["BLOCKED", "DECLINED", "REJECTED"].includes(normalized)) {
    return <Badge variant="danger">{status}</Badge>;
  }
  return <Badge>{status}</Badge>;
};

const filters = (label: string) => (
  <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 pb-4">
    <div className="w-60">
      <Input placeholder={`${label} ID / телефон / telegram_id`} />
    </div>
    <select className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900">
      <option>Все статусы</option>
      <option>NEW</option>
      <option>IN_REVIEW</option>
      <option>BLOCKED</option>
    </select>
    <select className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900">
      <option>Все типы</option>
      <option>ИСПОЛНИТЕЛЬ</option>
      <option>КОМПАНИЯ</option>
    </select>
  </div>
);

const ActionButton = ({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: typeof Check;
  onClick: () => void;
}) => (
  <Button variant="secondary" size="icon" aria-label={label} onClick={onClick}>
    <Icon className="h-4 w-4 text-slate-700" />
  </Button>
);

type Appeal = {
  id: number;
  review_id: number;
  master_id: number;
  company_id: number;
  status: string;
  created_at: string;
  updated_at: string;
  master_comment: string;
  company_comment: string;
  master_files_message_id: string | null;
  company_files_message_id: number | null;
  review_text: string;
  master_full_name: string;
  master_public_id: string;
  company_name: string;
  company_public_id: string;
};

export default function App() {
  const [active, setActive] = useState("dashboard");
  const [dialog, setDialog] = useState<DialogState>(defaultDialog);
  const [reason, setReason] = useState("");
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [selectedAppeal, setSelectedAppeal] = useState<Appeal | null>(null);
  const [loading, setLoading] = useState(false);

  const openDialog = (state: Omit<DialogState, "open">) => {
    setReason("");
    setDialog({ ...state, open: true });
  };

  const closeDialog = () => setDialog(defaultDialog);

  const pageTitle = useMemo(() => menuItems.find((item) => item.key === active)?.label, [active]);

  // Загрузка жалоб при открытии раздела споров
  useEffect(() => {
    if (active === "disputes") {
      setLoading(true);
      fetch("/api/review-appeals")
        .then((res) => res.json())
        .then((data) => {
          setAppeals(data);
          setLoading(false);
        })
        .catch((err) => {
          console.error("Ошибка загрузки жалоб:", err);
          setLoading(false);
        });
    }
  }, [active]);

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      <div className="flex min-h-screen">
        <aside className="w-60 border-r border-slate-200 bg-white">
          <div className="px-6 py-5">
            <p className="text-xs uppercase tracking-wide text-slate-500">Admin Panel</p>
            <p className="text-lg font-semibold">Belyi Spisok</p>
          </div>
          <nav className="space-y-1 px-3">
            {menuItems.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActive(key)}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  active === key
                    ? "bg-blue-50 text-blue-600"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </nav>
        </aside>

        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
            <div className="flex items-center gap-3">
              <Search className="h-4 w-4 text-slate-500" />
              <Input
                placeholder="Поиск: executor_id, company_id, request_id, signal_id, dispute_id, ticket_id"
                className="w-[420px]"
              />
            </div>
            <div className="text-sm text-slate-500">Admin • supervisor@belyispisok</div>
          </header>

          <main className="flex-1 space-y-6 px-6 py-6">
            <div>
              <h1 className="text-2xl font-semibold">{pageTitle}</h1>
              <p className="text-sm text-slate-500">Рабочая зона администратора</p>
            </div>

            {active === "dashboard" && (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {[
                    { label: "Новые исполнители", value: "24" },
                    { label: "Новые компании", value: "11" },
                    { label: "Ожидает верификации", value: "9" },
                    { label: "Новые споры", value: "4" },
                  ].map((card) => (
                    <Card key={card.label}>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-medium text-slate-500">{card.label}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-semibold text-slate-900">{card.value}</div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle>Быстрые действия</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-3">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setActive("disputes");
                      }}
                    >
                      Открыть новые споры
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setActive("verification");
                      }}
                    >
                      Компании на верификации
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setActive("access");
                      }}
                    >
                      Заблокированные компании
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setActive("support");
                      }}
                    >
                      Новые тикеты поддержки
                    </Button>
                  </CardContent>
                </Card>
              </div>
            )}

            {active === "registrations" && (
              <div className="space-y-6">
                {filters("reg")}
                <Card>
                  <CardHeader>
                    <CardTitle>Очередь регистраций</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Reg ID</TableHead>
                          <TableHead>Тип</TableHead>
                          <TableHead>Entity ID</TableHead>
                          <TableHead>Создано</TableHead>
                          <TableHead>Контакт</TableHead>
                          <TableHead>Статус</TableHead>
                          <TableHead>Risk</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {[
                          {
                            id: "REG-001",
                            type: "ИСПОЛНИТЕЛЬ",
                            entity: "M-103942",
                            created: "2024-10-12",
                            contact: "+7 913 000 11 22",
                            status: "NEW",
                            risk: "НЕТ",
                          },
                          {
                            id: "REG-002",
                            type: "КОМПАНИЯ",
                            entity: "C-540112",
                            created: "2024-10-12",
                            contact: "@company_hr",
                            status: "SENT_TO_VERIFICATION",
                            risk: "ПОДОЗРИТЕЛЬНО",
                          },
                        ].map((row) => (
                          <TableRow key={row.id}>
                            <TableCell className="font-mono">{row.id}</TableCell>
                            <TableCell>{row.type}</TableCell>
                            <TableCell className="font-mono">{row.entity}</TableCell>
                            <TableCell>{row.created}</TableCell>
                            <TableCell>{row.contact}</TableCell>
                            <TableCell>{statusBadge(row.status)}</TableCell>
                            <TableCell>{row.risk}</TableCell>
                            <TableCell className="text-right">
                              <div className="inline-flex gap-2">
                                <ActionButton
                                  label="Открыть"
                                  icon={FileText}
                                  onClick={() => {
                                    // Открыть детали регистрации
                                    console.log("Открыть регистрацию:", row.id);
                                  }}
                                />
                                <ActionButton
                                  label="Принять"
                                  icon={Check}
                                  onClick={() =>
                                    openDialog({
                                      title: "Принять регистрацию",
                                      description: "Регистрация будет помечена как REVIEWED.",
                                      confirmLabel: "Подтвердить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Отклонить"
                                  icon={X}
                                  onClick={() =>
                                    openDialog({
                                      title: "Отклонить регистрацию",
                                      description: "Регистрация будет отклонена и помечена как REJECTED.",
                                      confirmLabel: "Отклонить",
                                      variant: "danger",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Отправить на верификацию"
                                  icon={BadgeCheck}
                                  onClick={() =>
                                    openDialog({
                                      title: "Отправить на верификацию",
                                      description: "Регистрация компании перейдёт в очередь верификации.",
                                      confirmLabel: "Отправить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Пометить как подозрительную"
                                  icon={AlertCircle}
                                  onClick={() =>
                                    openDialog({
                                      title: "Пометить как подозрительную",
                                      description: "Регистрация получит флаг риска.",
                                      confirmLabel: "Подтвердить",
                                      variant: "primary",
                                    })
                                  }
                                />
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Карточка регистрации</CardTitle>
                  </CardHeader>
                  <CardContent className="grid gap-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">reg_id</span>
                      <span className="font-mono">REG-001</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">entity_id</span>
                      <span className="font-mono">M-103942</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">contact</span>
                      <span>+7 913 000 11 22</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">created_at</span>
                      <span>2024-10-12 10:21</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">consent_given</span>
                      <span>true</span>
                    </div>
                    <div className="space-y-2">
                      <span className="text-slate-500">admin_note</span>
                      <Textarea placeholder="Короткая заметка администратора" />
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {active === "verification" && (
              <div className="space-y-6">
                {filters("verif")}
                <Card>
                  <CardHeader>
                    <CardTitle>Очередь верификации</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Verif ID</TableHead>
                          <TableHead>Company ID</TableHead>
                          <TableHead>Создано</TableHead>
                          <TableHead>Статус</TableHead>
                          <TableHead>Required info</TableHead>
                          <TableHead>Last action</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {[
                          {
                            id: "VER-221",
                            company: "C-540112",
                            created: "2024-10-11",
                            status: "WAITING",
                            info: "Учредительные документы",
                            last: "2024-10-12",
                          },
                        ].map((row) => (
                          <TableRow key={row.id}>
                            <TableCell className="font-mono">{row.id}</TableCell>
                            <TableCell className="font-mono">{row.company}</TableCell>
                            <TableCell>{row.created}</TableCell>
                            <TableCell>{statusBadge(row.status)}</TableCell>
                            <TableCell>{row.info}</TableCell>
                            <TableCell>{row.last}</TableCell>
                            <TableCell className="text-right">
                              <div className="inline-flex gap-2">
                                <ActionButton
                                  label="Подтвердить"
                                  icon={Check}
                                  onClick={() =>
                                    openDialog({
                                      title: "Подтвердить верификацию",
                                      description: "Компания получит статус APPROVED.",
                                      confirmLabel: "Подтвердить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Отказать"
                                  icon={X}
                                  onClick={() =>
                                    openDialog({
                                      title: "Отказать в верификации",
                                      description: "Компания получит статус DECLINED.",
                                      confirmLabel: "Отказать",
                                      variant: "danger",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Запросить данные"
                                  icon={AlertCircle}
                                  onClick={() =>
                                    openDialog({
                                      title: "Запросить данные",
                                      description: "Статус изменится на NEED_INFO.",
                                      confirmLabel: "Запросить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Отменить"
                                  icon={X}
                                  onClick={() =>
                                    openDialog({
                                      title: "Отменить верификацию",
                                      description: "Статус изменится на CANCELLED.",
                                      confirmLabel: "Отменить",
                                      variant: "danger",
                                    })
                                  }
                                />
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Карточка верификации</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">company_id</span>
                      <span className="font-mono">C-540112</span>
                    </div>
                    <div>
                      <p className="text-slate-500">загруженные данные</p>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                        <li>Устав компании</li>
                        <li>Выписка из реестра</li>
                      </ul>
                    </div>
                    <div>
                      <p className="text-slate-500">история запросов</p>
                      <p className="text-sm text-slate-700">2024-10-12 • запрос на устав</p>
                    </div>
                    <div>
                      <p className="text-slate-500">решение</p>
                      <p className="text-sm text-slate-700">Ожидает проверки</p>
                    </div>
                    <div className="space-y-2">
                      <p className="text-slate-500">документы</p>
                      <div className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2">
                        <div>
                          <p className="text-sm text-slate-900">Фото паспорта</p>
                          <p className="text-xs text-slate-500">Хранится после решения</p>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() =>
                            openDialog({
                              title: "Показать документ",
                              description:
                                "Просмотр паспорта фиксируется в журнале действий. Укажите причину доступа.",
                              confirmLabel: "Показать",
                              variant: "primary",
                            })
                          }
                        >
                          Показать документ
                        </Button>
                      </div>
                      <div className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2">
                        <div>
                          <p className="text-sm text-slate-900">Видео с паспортом</p>
                          <p className="text-xs text-slate-500">Удаляется после решения</p>
                        </div>
                        <Badge variant="warning">ДО РЕШЕНИЯ</Badge>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <p className="text-slate-500">комментарий админа</p>
                      <Textarea placeholder="Причина решения или комментарий" />
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {active === "access" && (
              <div className="space-y-6">
                {filters("company")}
                <Card>
                  <CardHeader>
                    <CardTitle>Список компаний</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Company ID</TableHead>
                          <TableHead>Access status</TableHead>
                          <TableHead>Check limit</TableHead>
                          <TableHead>Checks used</TableHead>
                          <TableHead>Auto block</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {[
                          {
                            id: "C-440221",
                            status: "ACTIVE",
                            limit: "120",
                            used: "54",
                            autoBlock: "true",
                          },
                          {
                            id: "C-540112",
                            status: "BLOCKED",
                            limit: "60",
                            used: "61",
                            autoBlock: "true",
                          },
                        ].map((row) => (
                          <TableRow key={row.id}>
                            <TableCell className="font-mono">{row.id}</TableCell>
                            <TableCell>{statusBadge(row.status)}</TableCell>
                            <TableCell>{row.limit}</TableCell>
                            <TableCell>{row.used}</TableCell>
                            <TableCell>{row.autoBlock}</TableCell>
                            <TableCell className="text-right">
                              <div className="inline-flex gap-2">
                                <ActionButton
                                  label="Разрешить доступ вручную"
                                  icon={Check}
                                  onClick={() =>
                                    openDialog({
                                      title: "Разрешить доступ вручную",
                                      description: "Компания получит статус MANUAL_ALLOWED.",
                                      confirmLabel: "Разрешить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Убрать ручное разрешение"
                                  icon={X}
                                  onClick={() =>
                                    openDialog({
                                      title: "Убрать ручное разрешение",
                                      description: "Компания вернётся к автоматической подписке.",
                                      confirmLabel: "Подтвердить",
                                      variant: "danger",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Изменить лимит"
                                  icon={FileText}
                                  onClick={() =>
                                    openDialog({
                                      title: "Изменить лимит",
                                      description: "Укажите причину изменения лимита.",
                                      confirmLabel: "Сохранить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Заблокировать"
                                  icon={Lock}
                                  onClick={() =>
                                    openDialog({
                                      title: "Заблокировать компанию",
                                      description: "Доступ компании будет заблокирован.",
                                      confirmLabel: "Заблокировать",
                                      variant: "danger",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Разблокировать"
                                  icon={Unlock}
                                  onClick={() =>
                                    openDialog({
                                      title: "Разблокировать компанию",
                                      description: "Доступ компании будет восстановлен.",
                                      confirmLabel: "Разблокировать",
                                      variant: "primary",
                                    })
                                  }
                                />
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Карточка доступа компании</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-500">company_id</span>
                      <span className="font-mono">C-440221</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">access_status</span>
                      <span>{statusBadge("ACTIVE")}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">лимиты</span>
                      <span>120 проверок / месяц</span>
                    </div>
                    <div>
                      <p className="text-slate-500">история ручных вмешательств</p>
                      <p className="text-sm text-slate-700">2024-09-28 • установлен лимит 120</p>
                    </div>
                    <div>
                      <p className="text-slate-500">последние проверки</p>
                      <p className="text-sm text-slate-700">2024-10-12 • проверка M-103942</p>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {active === "disputes" && (
              <div className="space-y-6">
                {filters("dispute")}
                <Card>
                  <CardHeader>
                    <CardTitle>Очередь жалоб на отзывы</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {loading ? (
                      <div className="py-8 text-center text-slate-500">Загрузка...</div>
                    ) : appeals.length === 0 ? (
                      <div className="py-8 text-center text-slate-500">Нет жалоб</div>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Appeal ID</TableHead>
                            <TableHead>Review ID</TableHead>
                            <TableHead>Executor</TableHead>
                            <TableHead>Company</TableHead>
                            <TableHead>Статус</TableHead>
                            <TableHead>Создано</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {appeals.map((appeal) => (
                            <TableRow
                              key={appeal.id}
                              className={selectedAppeal?.id === appeal.id ? "bg-blue-50" : ""}
                              onClick={() => setSelectedAppeal(appeal)}
                            >
                              <TableCell className="font-mono">#{appeal.id}</TableCell>
                              <TableCell className="font-mono">#{appeal.review_id}</TableCell>
                              <TableCell className="font-mono">
                                {appeal.master_full_name} ({appeal.master_public_id})
                              </TableCell>
                              <TableCell className="font-mono">
                                {appeal.company_name || "-"} ({appeal.company_public_id || "-"})
                              </TableCell>
                              <TableCell>{statusBadge(appeal.status)}</TableCell>
                              <TableCell>{new Date(appeal.created_at).toLocaleDateString("ru-RU")}</TableCell>
                              <TableCell className="text-right">
                                <div className="inline-flex gap-2">
                                  <ActionButton
                                    label="Открыть"
                                    icon={FileText}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedAppeal(appeal);
                                    }}
                                  />
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </CardContent>
                </Card>

                {selectedAppeal && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Карточка жалобы #{selectedAppeal.id}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-500">appeal_id</span>
                        <span className="font-mono">#{selectedAppeal.id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">review_id</span>
                        <span className="font-mono">#{selectedAppeal.review_id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">executor</span>
                        <span className="font-mono">
                          {selectedAppeal.master_full_name} ({selectedAppeal.master_public_id})
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">company</span>
                        <span className="font-mono">
                          {selectedAppeal.company_name || "-"} ({selectedAppeal.company_public_id || "-"})
                        </span>
                      </div>
                      <div>
                        <p className="text-slate-500">текст отзыва</p>
                        <p className="text-slate-700">{selectedAppeal.review_text}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">жалоба исполнителя</p>
                        <p className="text-slate-700">{selectedAppeal.master_comment || "не указано"}</p>
                      </div>
                      {selectedAppeal.company_comment && (
                        <div>
                          <p className="text-slate-500">ответ компании</p>
                          <p className="text-slate-700">{selectedAppeal.company_comment}</p>
                        </div>
                      )}
                      <div>
                        <p className="text-slate-500">материалы</p>
                        <div className="mt-2 space-y-2">
                          {selectedAppeal.master_files_message_id && (
                            <div>
                              <p className="text-xs text-slate-500">Фото от исполнителя:</p>
                              <p className="text-xs text-slate-700">
                                {(() => {
                                  try {
                                    const photos = JSON.parse(selectedAppeal.master_files_message_id);
                                    return Array.isArray(photos) ? `${photos.length} фото` : "1 фото";
                                  } catch {
                                    return "1 фото";
                                  }
                                })()}
                              </p>
                            </div>
                          )}
                          {selectedAppeal.company_files_message_id && (
                            <div>
                              <p className="text-xs text-slate-500">Фото от компании:</p>
                              <p className="text-xs text-slate-700">1 файл</p>
                            </div>
                          )}
                          {!selectedAppeal.master_files_message_id && !selectedAppeal.company_files_message_id && (
                            <p className="text-xs text-slate-500">Нет прикрепленных файлов</p>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}

            {active === "support" && (
              <div className="space-y-6">
                {filters("ticket")}
                <Card>
                  <CardHeader>
                    <CardTitle>Очередь тикетов</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Ticket ID</TableHead>
                          <TableHead>Автор</TableHead>
                          <TableHead>Категория</TableHead>
                          <TableHead>Статус</TableHead>
                          <TableHead>Создано</TableHead>
                          <TableHead>Last message</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {[
                          {
                            id: "T-9902",
                            author: "ИСПОЛНИТЕЛЬ • M-103942",
                            category: "LOGIN",
                            status: "NEW",
                            created: "2024-10-12",
                            last: "2024-10-12 09:40",
                          },
                        ].map((row) => (
                          <TableRow key={row.id}>
                            <TableCell className="font-mono">{row.id}</TableCell>
                            <TableCell>{row.author}</TableCell>
                            <TableCell>{row.category}</TableCell>
                            <TableCell>{statusBadge(row.status)}</TableCell>
                            <TableCell>{row.created}</TableCell>
                            <TableCell>{row.last}</TableCell>
                            <TableCell className="text-right">
                              <div className="inline-flex gap-2">
                                <ActionButton
                                  label="Ответить"
                                  icon={Check}
                                  onClick={() =>
                                    openDialog({
                                      title: "Ответить пользователю",
                                      description: "Ответ будет добавлен в тикет.",
                                      confirmLabel: "Отправить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Запросить данные"
                                  icon={AlertCircle}
                                  onClick={() =>
                                    openDialog({
                                      title: "Запросить данные",
                                      description: "Статус станет WAITING_USER.",
                                      confirmLabel: "Запросить",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Создать спор"
                                  icon={Scale}
                                  onClick={() =>
                                    openDialog({
                                      title: "Создать спор",
                                      description: "На основании тикета будет создан спор.",
                                      confirmLabel: "Создать",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Привязать к сущности"
                                  icon={FileText}
                                  onClick={() =>
                                    openDialog({
                                      title: "Привязать к сущности",
                                      description: "Тикет будет связан с выбранной сущностью.",
                                      confirmLabel: "Привязать",
                                      variant: "primary",
                                    })
                                  }
                                />
                                <ActionButton
                                  label="Закрыть тикет"
                                  icon={X}
                                  onClick={() =>
                                    openDialog({
                                      title: "Закрыть тикет",
                                      description: "Тикет будет закрыт со статусом CLOSED.",
                                      confirmLabel: "Закрыть",
                                      variant: "danger",
                                    })
                                  }
                                />
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Карточка тикета</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    <div>
                      <p className="text-slate-500">сообщения</p>
                      <div className="space-y-2 text-slate-700">
                        <p>Пользователь не может войти в аккаунт.</p>
                        <p className="text-slate-500">Админ: требуется уточнить телефон.</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-slate-500">связанные сущности</p>
                      <p className="text-slate-700">signal_id: S-2201, dispute_id: D-4001</p>
                    </div>
                    <div className="space-y-2">
                      <p className="text-slate-500">internal_note</p>
                      <Textarea placeholder="Внутренняя заметка" />
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {active === "search" && (
              <div className="space-y-6">
                <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 pb-4">
                  <div className="w-72">
                    <Input placeholder="Поиск по ID, телефону, telegram_id" />
                  </div>
                  <select className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900">
                    <option>Исполнитель</option>
                    <option>Компания</option>
                    <option>Запрос</option>
                    <option>Сигнал</option>
                    <option>Спор</option>
                    <option>Тикет</option>
                    <option>Контакт</option>
                  </select>
                  <Button variant="secondary">Найти</Button>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle>Результаты поиска</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>ID</TableHead>
                          <TableHead>Тип</TableHead>
                          <TableHead>Статус</TableHead>
                          <TableHead>Создано</TableHead>
                          <TableHead>Обновлено</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        <TableRow>
                          <TableCell className="font-mono">M-103942</TableCell>
                          <TableCell>Исполнитель</TableCell>
                          <TableCell>{statusBadge("ACTIVE")}</TableCell>
                          <TableCell>2024-01-20</TableCell>
                          <TableCell>2024-10-12</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="font-mono">C-540112</TableCell>
                          <TableCell>Компания</TableCell>
                          <TableCell>{statusBadge("BLOCKED")}</TableCell>
                          <TableCell>2024-03-11</TableCell>
                          <TableCell>2024-10-10</TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle>Карточка исполнителя</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-500">executor_id</span>
                        <span className="font-mono">M-103942</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">status</span>
                        <span>{statusBadge("ACTIVE")}</span>
                      </div>
                      <div>
                        <p className="text-slate-500">сигналы</p>
                        <p className="text-slate-700">2 активных сигнала</p>
                      </div>
                      <div>
                        <p className="text-slate-500">запросы сотрудничества</p>
                        <p className="text-slate-700">1 активный запрос</p>
                      </div>
                      <div>
                        <p className="text-slate-500">открытые споры</p>
                        <p className="text-slate-700">1 спор</p>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>Карточка компании</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-500">company_id</span>
                        <span className="font-mono">C-540112</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">access_status</span>
                        <span>{statusBadge("BLOCKED")}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">лимиты</span>
                        <span>60 проверок / месяц</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-500">статус верификации</span>
                        <span>{statusBadge("NEED_INFO")}</span>
                      </div>
                      <div>
                        <p className="text-slate-500">сигналы компании</p>
                        <p className="text-slate-700">3 сигнала</p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            )}
          </main>
        </div>
      </div>

      <Dialog open={dialog.open} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{dialog.title}</DialogTitle>
            <DialogDescription>{dialog.description}</DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-2">
            <label className="text-sm font-medium text-slate-700">Причина</label>
            <Textarea
              placeholder="Укажите причину действия"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required
            />
            <p className="text-xs text-slate-500">Все действия админа фиксируются в action_log.</p>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary" type="button">
                Отменить
              </Button>
            </DialogClose>
            <Button
              variant={dialog.variant}
              type="button"
              onClick={() => {
                if (reason.trim()) {
                  // Здесь можно добавить вызов API для выполнения действия
                  console.log("Действие:", dialog.title, "Причина:", reason);
                  closeDialog();
                } else {
                  alert("Пожалуйста, укажите причину действия");
                }
              }}
            >
              {dialog.confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
