// src/components/RelicToggle.tsx
import "./RelicToggle.css";

interface RelicToggleProps {
  label: string;
  active: boolean;
  onChange: () => void;
}

const RelicToggle: React.FC<RelicToggleProps> = ({
  label,
  active,
  onChange,
}) => {
  return (
    <div className="relic-toggle-container" onClick={onChange}>
      <div className={`relic-box ${active ? "on" : "off"}`}></div>
      <span className="relic-label">{label}</span>
    </div>
  );
};

export default RelicToggle;
