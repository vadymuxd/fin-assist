type Props = {
  direction: "left" | "right";
  onClick: () => void;
  disabled?: boolean;
};

const chevronLeft = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 18 9 12 15 6" />
  </svg>
);

const chevronRight = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export default function NavBtn({ direction, onClick, disabled }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center justify-center w-8 h-8 rounded-md border border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-900 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
    >
      {direction === "left" ? chevronLeft : chevronRight}
    </button>
  );
}
