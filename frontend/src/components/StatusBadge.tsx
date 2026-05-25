

interface StatusBadgeProps {
  status: string;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  let badgeClass = "badge";
  let displayStatus = status;

  switch (status?.toLowerCase()) {
    case 'pending':
      badgeClass += " pending";
      break;
    case 'approved':
      badgeClass += " approved";
      break;
    case 'rejected':
      badgeClass += " rejected";
      break;
    case 'suspicious':
      badgeClass += " suspicious";
      break;
    case 'completed':
      badgeClass += " approved";
      break;
    case 'failed':
      badgeClass += " rejected";
      break;
    default:
      badgeClass += " info";
  }

  return <span className={badgeClass}>{displayStatus}</span>;
}
